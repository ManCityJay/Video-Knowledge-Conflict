#!/usr/bin/env python3
"""Sweep lambda on a frozen manifest; one shared lambda=0 baseline per item."""
import argparse
import collections
import fcntl
import hashlib
import json
import math
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mcd_v1.run_mcd_v1 import main as run_one
from mcd_v1.run_mcd_v1_batch import code_fingerprints, read_json
from mcd_v1.storage import write_json
from vconflict_pipeline.core import atomic_write_text

WEIGHTS = (0.0, 0.1, 0.2, 0.3, 0.5)


def result_path(output, item, weight):
    return output / ("lambda_" + format(weight, "g")) / (item["id"] + ".json")


def make_report(manifest, output):
    rows, summary = [], {}
    for weight in WEIGHTS:
        counts = collections.Counter()
        seconds = 0.0
        for item in manifest["items"]:
            path = result_path(output, item, weight)
            data = read_json(path) if path.exists() else {}
            answer = data.get("runs", {}).get("mcd_v1", {})
            status = "error" if data.get("error") else answer.get("status", "pending")
            counts[status] += 1
            seconds += answer.get("seconds", 0)
            rows.append({**item, "lambda": weight, "status": status,
                         "answer": answer, "error": data.get("error"),
                         "result_file": str(path),
                         "baseline_file": str(result_path(output, item, 0))})
        summary[str(weight)] = {"statuses": dict(counts), "generation_seconds": round(seconds, 3)}
    atomic_write_text(output / "report.json", json.dumps(rows, ensure_ascii=False, indent=2) + "\n")
    atomic_write_text(output / "summary.json", json.dumps(summary, indent=2) + "\n")
    lines = ["# Lambda sweep", "",
             "Same 20-item pilot when using the original manifest. Lambda 0 is the shared greedy baseline.",
             "Status is format/completion only, not correctness. format_fallback needs manual review.",
             "Compare final answer and explanation separately; references are unverified and are never model inputs.", "",
             "| Item | Role | Reference | lambda=0 | 0.1 | 0.2 | 0.3 | 0.5 |",
             "|---|---|---|---|---|---|---|---|"]
    def cell(value):
        return str(value or "").replace("|", "\\|").replace("\n", "<br>")
    by_key = {(r["id"], r["lambda"]): r for r in rows}
    for item in manifest["items"]:
        values = [item["id"], item["role"], item["reference"]]
        for weight in WEIGHTS:
            row = by_key[item["id"], weight]
            answer = row["answer"]
            values.append("[" + row["status"] + "] " + (answer.get("evaluation_answer") or answer.get("final_answer") or ""))
        lines.append("| " + " | ".join(cell(v) for v in values) + " |")
    atomic_write_text(output / "report.md", "\n".join(lines) + "\n")
    return summary


def execute(args, manifest, output):
    fingerprints = code_fingerprints()
    fingerprints["mcd_v1/run_lambda_sweep.py"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    config = {k: getattr(args, k) for k in ("model", "revision", "device", "dtype", "beta", "fps", "max_new_tokens")}
    config.update(weights=list(WEIGHTS), thinking_effort="none",
                  manifest_sha256=hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest(),
                  code_sha256=fingerprints)
    config_path = output / "config.json"
    if config_path.exists():
        if read_json(config_path) != config:
            raise ValueError("Config, code or manifest changed; use a new output directory.")
        if read_json(output / "manifest.json") != manifest:
            raise ValueError("Saved manifest changed.")
    else:
        if any(p.name != ".sweep.lock" for p in output.iterdir()):
            raise ValueError("New sweep requires an empty output directory.")
        write_json(output / "manifest.json", manifest)
        write_json(config_path, config)
    for weight in WEIGHTS:
        result_path(output, manifest["items"][0], weight).parent.mkdir(exist_ok=True)
    if args.prepare_only:
        make_report(manifest, output)
        print(f"Prepared {len(manifest['items'])} items x {len(WEIGHTS)} lambdas; no model loaded.")
        return 0
    runtime = {}
    total = len(manifest["items"]) * len(WEIGHTS)
    index = 0
    for item in manifest["items"]:
        for weight in WEIGHTS:
            index += 1
            target = result_path(output, item, weight)
            if target.exists():
                print(f"[{index}/{total}] Preserve {item['id']} lambda={weight}", flush=True)
                continue
            print(f"[{index}/{total}] Run {item['id']} lambda={weight}", flush=True)
            command = ["--video", item["video"], "--question", item["question"],
                       "--model", args.model, "--device", args.device, "--dtype", args.dtype,
                       "--lambda", str(weight), "--beta", str(args.beta), "--fps", str(args.fps),
                       "--max-new-tokens", str(args.max_new_tokens), "--output", str(target)]
            if args.revision:
                command.extend(["--revision", args.revision])
            # No compare-baseline: lambda=0 is generated exactly once per item.
            try:
                run_one(command, runtime=runtime)
            except Exception as exc:
                if not target.exists():
                    write_json(target, {"error": {"type": type(exc).__name__, "message": str(exc)}, "runs": {}})
                raise
            finally:
                make_report(manifest, output)
            if read_json(target).get("error"):
                raise RuntimeError(f"Generation error saved in {target}; inspect before continuing.")
    summary = make_report(manifest, output)
    print(json.dumps(summary, indent=2), flush=True)
    print(f"Report: {output / 'report.md'}", flush=True)
    return int(any(any(k not in ("ok", "format_fallback") and v for k, v in group["statuses"].items())
                   for group in summary.values()))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--revision")
    parser.add_argument("--device", default="cuda:1")
    parser.add_argument("--dtype", choices=("bfloat16", "float16", "float32"), default="bfloat16")
    parser.add_argument("--beta", type=float, default=0.1)
    parser.add_argument("--fps", type=float, default=4)
    parser.add_argument("--max-new-tokens", type=int, default=512)
    parser.add_argument("--prepare-only", action="store_true")
    args = parser.parse_args(argv)
    if not math.isfinite(args.beta) or not 0 <= args.beta <= 1 or not math.isfinite(args.fps) or args.fps <= 0 or args.max_new_tokens <= 0:
        parser.error("Invalid beta, fps or token limit")
    manifest = read_json(args.manifest)
    items = manifest.get("items", [])
    ids = [i["id"] for i in items]
    if not items or len(ids) != len(set(ids)) or any(not i or Path(i).name != i or i in (".", "..") for i in ids):
        parser.error("Invalid manifest IDs")
    for item in items:
        if not Path(item["video"]).is_file() or not item["question"].strip():
            parser.error(f"Missing video or question: {item['id']}")
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    with (output / ".sweep.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            parser.error("Another sweep is already using this output directory.")
        try:
            return execute(args, manifest, output)
        except ValueError as exc:
            parser.error(str(exc))


if __name__ == "__main__":
    raise SystemExit(main())
