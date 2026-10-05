#!/usr/bin/env python3
"""Small, sequential Cosmos MCD experiment with a frozen sample list."""
import argparse
import hashlib
import json
import math
import random
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mcd_v1.run_mcd_v1 import main as run_one
from mcd_v1.storage import write_json
from vconflict_pipeline.core import atomic_write_text, resolve_video_path
from vconflict_pipeline.settings import PROJECT_ROOT, COSMOS_QA_MODEL


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def usable(video):
    return (video.get("status") == "ready"
            and video.get("human_review") != "rejected"
            and bool(video.get("local_path"))
            and resolve_video_path(video["local_path"]).is_file())


def select_samples(case_dir, count=5, seed=42):
    pools = {"knowledge_trapped": [], "context_grounded": []}
    for path in sorted(case_dir.glob("*.json")):
        case = read_json(path)
        controls = [v for v in case["videos"] if v["role"] == "control" and usable(v)]
        # V1 requires an unambiguous original-case control. Variant contexts
        # need explicit pairing and are deliberately excluded from this pilot.
        if len(controls) != 1 or controls[0].get("variant_context"):
            continue
        control = controls[0]
        for video in case["videos"]:
            if video["role"] != "conflict" or not usable(video) or video.get("variant_context"):
                continue
            for question in case["questions"]:
                history = [r for r in video.get("qa_results", [])
                           if r.get("model") == COSMOS_QA_MODEL
                           and r.get("thinking_effort") in (None, "none")
                           and r.get("input_mode") == "video"
                           and r.get("question_id") == question["question_id"]
                           and r.get("question") == question["text_en"]
                           and not r.get("based")
                           and not r.get("work_title_prefix")]
                if not history:
                    continue
                latest = max(history, key=lambda r: r.get("timestamp", ""))
                verdict = (latest.get("judgment") or {}).get("verdict")
                if verdict not in pools or latest.get("error") or not latest.get("final_answer"):
                    continue
                if not question.get("conflict_video_reference_en") or not question.get("normal_control_reference_en"):
                    continue
                pools[verdict].append({
                    "case_id": case["case_id"], "case_file": str(path.resolve()),
                    "question_id": question["question_id"], "question": question["text_en"],
                    "historical_verdict": verdict,
                    "historical_run_id": latest.get("run_id"),
                    "historical_timestamp": latest.get("timestamp"),
                    "historical_answer": latest["final_answer"],
                    "conflict": {"video_id": video["video_id"], "video": str(resolve_video_path(video["local_path"])),
                                 "human_review": video.get("human_review"),
                                 "reference": question["conflict_video_reference_en"]},
                    "control": {"video_id": control["video_id"], "video": str(resolve_video_path(control["local_path"])),
                                "human_review": control.get("human_review"),
                                "reference": question["normal_control_reference_en"]},
                })
    selected, used_cases = [], set()
    rng = random.Random(seed)
    for verdict, pool in pools.items():
        if len(pool) < count:
            raise ValueError(f"Not enough eligible {verdict}: {len(pool)} < {count}")
        rng.shuffle(pool)
        chosen = []
        for item in pool:
            if item["case_id"] not in used_cases:
                chosen.append(item)
                used_cases.add(item["case_id"])
                if len(chosen) == count:
                    break
        for item in pool:
            if len(chosen) == count:
                break
            if item not in chosen:
                chosen.append(item)
        selected.extend(chosen)
    items, controls = [], {}
    for i, pair in enumerate(selected, 1):
        pair_id = f"pair_{i:02d}"
        common = {k: v for k, v in pair.items() if k not in ("conflict", "control")}
        conflict = {**common, **pair["conflict"], "id": f"conflict_{i:02d}", "role": "conflict", "pairs": [pair_id]}
        items.append(conflict)
        key = (pair["control"]["video"], pair["question"])
        if key not in controls:
            controls[key] = {**common, **pair["control"], "id": f"control_{i:02d}",
                             "role": "control", "pairs": [], "historical_verdict": "matched_control"}
            for field in ("historical_run_id", "historical_timestamp", "historical_answer"):
                controls[key].pop(field, None)
        controls[key]["pairs"].append(pair_id)
        conflict["control_id"] = controls[key]["id"]
    items.extend(controls.values())
    return {"schema": "mcd_pilot_v1", "seed": seed, "per_group": count,
            "eligible_counts": {k: len(v) for k, v in pools.items()},
            "note": "Historical judgments only select samples. Pending human review is allowed. Original cases only; variants excluded. Controls use the identical question. This balanced pilot is not an overall accuracy estimate.",
            "items": items}


def successful(result):
    return (not result.get("error")
            and result.get("lambda_zero_matches") is not False
            and all(result.get("runs", {}).get(k, {}).get("status") == "ok"
                    for k in ("baseline", "mcd_v1")))


def result_status(result):
    if successful(result):
        return "ok"
    if not result:
        return "pending"
    statuses = [result.get("runs", {}).get(k, {}).get("status")
                for k in ("baseline", "mcd_v1")]
    if (not result.get("error") and result.get("lambda_zero_matches") is not False
            and all(s in ("ok", "format_fallback") for s in statuses)):
        return "format_fallback"
    return "truncated" if "truncated" in statuses else "failed"


def report(manifest, output):
    rows = []
    for item in manifest["items"]:
        path = output / (item["id"] + ".json")
        result = read_json(path) if path.exists() else {}
        runs = result.get("runs", {})
        rows.append({**item, "result_file": str(path),
                     "status": result_status(result),
                     "max_new_tokens": result.get("max_new_tokens"),
                     "recovery": result.get("recovery"),
                     "baseline": runs.get("baseline", {}), "mcd_v1": runs.get("mcd_v1", {}),
                     "error": result.get("error")})
    # Only derived reports are replaced; model responses and manual notes stay untouched.
    atomic_write_text(output / "report.json", json.dumps(rows, ensure_ascii=False, indent=2) + "\n")
    lines = ["# MCD v1 pilot", "", manifest["note"], "",
             "Compare fresh baseline and CD against the video. Status ok means decoding/parsing succeeded, not that the answer is correct. format_fallback retains the full response for manual evaluation; it is not a standard parsed answer.", "",
             "| Item | Role / historical group | Status | Reference | Baseline | CD |", "|---|---|---|---|---|---|"]
    def cell(value):
        return str(value or "").replace("|", "\\|").replace("\n", "<br>")
    for r in rows:
        lines.append("| " + " | ".join(map(cell, [r["id"], r["role"] + " / " + r["historical_verdict"], r["status"], r["reference"],
            r["baseline"].get("evaluation_answer") or r["baseline"].get("final_answer"), r["mcd_v1"].get("evaluation_answer") or r["mcd_v1"].get("final_answer")])) + " |")
    atomic_write_text(output / "report.md", "\n".join(lines) + "\n")
    return rows


def code_fingerprints():
    """Include shared prompt/path code so a resume cannot mix implementations."""
    script_dir = Path(__file__).resolve().parents[1]
    paths = (
        "mcd_v1/run_mcd_v1.py", "mcd_v1/run_mcd_v1_batch.py",
        "mcd_v1/decoding.py", "mcd_v1/storage.py",
        "vconflict_pipeline/qa.py", "vconflict_pipeline/core.py",
        "vconflict_pipeline/settings.py",
    )
    return {name: hashlib.sha256((script_dir / name).read_bytes()).hexdigest() for name in paths}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output-dir", type=Path, required=True)
    p.add_argument("--case-dir", type=Path, default=PROJECT_ROOT / "dataset/cases/classic_physics_chemistry_experiments")
    p.add_argument("--per-group", type=int, default=5)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--prepare-only", action="store_true")
    p.add_argument("--model", default=COSMOS_QA_MODEL)
    p.add_argument("--revision")
    p.add_argument("--device", default="cuda:0")
    p.add_argument("--dtype", choices=("bfloat16", "float16", "float32"), default="bfloat16")
    p.add_argument("--lambda", dest="weight", type=float, default=0.5)
    p.add_argument("--beta", type=float, default=0.1)
    p.add_argument("--fps", type=float, default=4.0)
    p.add_argument("--max-new-tokens", type=int, default=256)
    args = p.parse_args(argv)
    if (args.per_group < 1 or args.max_new_tokens < 1 or not math.isfinite(args.weight)
            or args.weight < 0 or not math.isfinite(args.beta) or not 0 <= args.beta <= 1
            or not math.isfinite(args.fps) or args.fps <= 0):
        p.error("Invalid count, lambda, beta, fps or token limit")
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    manifest_path = output / "manifest.json"
    if manifest_path.exists():
        manifest = read_json(manifest_path)
    else:
        if any(output.iterdir()):
            p.error("Choose an empty output directory; no manifest exists here")
        try:
            manifest = select_samples(args.case_dir, args.per_group, args.seed)
        except ValueError as exc:
            p.error(str(exc))
        write_json(manifest_path, manifest)
    items = manifest["items"]
    ids = [item["id"] for item in items]
    if (manifest.get("schema") != "mcd_pilot_v1" or not items or len(ids) != len(set(ids))
            or any(Path(i).name != i or i in (".", "..") for i in ids)):
        p.error("Invalid manifest")
    for item in items:
        if not Path(item["video"]).is_file() or not item["question"].strip():
            p.error(f"Missing video or question: {item['id']}")
    print(f"Frozen samples: {len(items)} video/question units; {manifest_path}", flush=True)
    if args.prepare_only:
        report(manifest, output)
        return 0
    config = {k: getattr(args, k) for k in ("model", "revision", "device", "dtype", "weight", "beta", "fps", "max_new_tokens")}
    config["manifest_sha256"] = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    config["code_sha256"] = code_fingerprints()
    config_path = output / "config.json"
    if config_path.exists():
        if read_json(config_path) != config:
            p.error("Configuration, code or manifest changed. Use a new output directory.")
    else:
        if any((output / (item["id"] + ".json")).exists() for item in items):
            p.error("Existing results have no config.json. Use a new output directory and copy only manifest.json.")
        write_json(config_path, config)
    runtime = {}
    for index, item in enumerate(items, 1):
        target = output / (item["id"] + ".json")
        if target.exists():
            print(f"[{index}/{len(items)}] Preserving existing result: {item['id']}", flush=True)
            continue
        print(f"[{index}/{len(items)}] {item['id']} {item['case_id']} {item['question_id']}", flush=True)
        command = ["--video", item["video"], "--question", item["question"], "--compare-baseline",
                   "--output", str(target), "--model", args.model, "--device", args.device,
                   "--dtype", args.dtype, "--lambda", str(args.weight), "--beta", str(args.beta),
                   "--fps", str(args.fps), "--max-new-tokens", str(args.max_new_tokens)]
        if args.revision:
            command.extend(["--revision", args.revision])
        try:
            run_one(command, runtime=runtime)
        except Exception as exc:
            if not target.exists():
                write_json(target, {"error": {"type": type(exc).__name__, "message": str(exc)}, "runs": {}})
            report(manifest, output)
            raise  # Stop on load/preprocessing errors instead of repeating failures.
        report(manifest, output)
    rows = report(manifest, output)
    bad = sum(r["status"] != "ok" for r in rows)
    print(f"Finished: {len(rows) - bad}/{len(rows)} decoded successfully. Report: {output / 'report.md'}")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
