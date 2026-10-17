#!/usr/bin/env python3
"""Run a QA/Judge model matrix; default to the three cloud models."""
from __future__ import annotations

import argparse
import json
import math
import os
import shlex
import subprocess
import sys
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import TextIO

# Keep the pipeline package importable when this file is launched directly.
RUNNER_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(RUNNER_DIR.parent))

from vconflict_pipeline.settings import (
    DEFAULT_COSMOS_WORKERS,
    DEFAULT_GEMMA_WORKERS,
    FAIRY_TALE_GROUP,
    PROJECT_ROOT,
)


CLOSED_MODELS = ("gemini", "qwen3.8-max", "kimi-k3")
LOCAL_MODELS = {
    "cosmos3-nano": DEFAULT_COSMOS_WORKERS,
    "gemma4": DEFAULT_GEMMA_WORKERS,
    "qwen3.8-27b": 4,
}
MODELS = (*CLOSED_MODELS, *LOCAL_MODELS)
MODEL_ALIASES = {"cosmos": "cosmos3-nano", "gemma": "gemma4"}
GROUPS = (
    FAIRY_TALE_GROUP,
    "classic_physics_chemistry_experiments",
    "real_world_commonsense_conflicts",
    "mathematics_algorithm_conflicts",
)
CONDITIONS = {
    "video": ("video", False),
    "video-based": ("video", True),
    "description": ("description", False),
    "description-based": ("description", True),
}
SHARED_FIELDS = (
    "judge_concurrency", "judge_rpm", "openrouter_concurrency",
    "openrouter_rpm", "timeout", "max_retries",
)
QA_FIELDS = ("qa_concurrency", "qa_service_concurrency", "qa_rpm")
API_KEYS = {
    "gemini": "OPENROUTER_API_KEY",
    "qwen3.8-max": "DASHSCOPE_API_KEY",
    "kimi-k3": "MOONSHOT_API_KEY",
}


def project_path(path: Path) -> Path:
    path = path.expanduser()
    return (path if path.is_absolute() else PROJECT_ROOT / path).resolve()


def load_config(path: Path) -> dict:
    config = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(config, dict) or set(config) != {*SHARED_FIELDS, "models"}:
        raise ValueError(f"Config must contain {', '.join(SHARED_FIELDS)} and models")
    models = config["models"]
    if (not isinstance(models, dict) or not set(CLOSED_MODELS).issubset(models)
            or not set(models).issubset(MODELS)):
        raise ValueError(
            f"Config models must include {', '.join(CLOSED_MODELS)}; "
            f"optional local models: {', '.join(LOCAL_MODELS)}")
    # Existing cloud-only config files keep working; local entries are optional.
    for model, concurrency in LOCAL_MODELS.items():
        models.setdefault(model, {
            "qa_concurrency": concurrency,
            "qa_service_concurrency": concurrency,
            "qa_rpm": 0,
        })
    options = [("shared", {field: config[field] for field in SHARED_FIELDS})]
    for model in MODELS:
        if not isinstance(models[model], dict) or set(models[model]) != set(QA_FIELDS):
            raise ValueError(f"Config {model} must contain {', '.join(QA_FIELDS)}")
        options.append((model, models[model]))
    for scope, values in options:
        for field, value in values.items():
            if field.endswith("rpm"):
                valid = (type(value) in (int, float)
                         and math.isfinite(value) and value >= 0)
                requirement = "a finite nonnegative number"
            else:
                minimum = 0 if field == "max_retries" else 1
                valid = type(value) is int and value >= minimum
                requirement = f"an integer >= {minimum}"
            if not valid:
                raise ValueError(f"Config {scope}.{field} must be {requirement}")
    return config


def build_plan(args: argparse.Namespace, config: dict) -> list[tuple[str, list[str]]]:
    models = CLOSED_MODELS if args.model == "all" else (args.model,)
    groups = tuple(dict.fromkeys(args.group or GROUPS))
    conditions = tuple(dict.fromkeys(args.condition or CONDITIONS))
    plan = []
    for model in models:
        # Qwen Max and all local models run both none and default efforts.
        effort = "all" if model == "qwen3.8-max" or model in LOCAL_MODELS else "default"
        limits = {field: config[field] for field in SHARED_FIELDS}
        limits.update(config["models"][model])
        for group in groups:
            for condition in conditions:
                input_mode, based = CONDITIONS[condition]
                command = [
                    sys.executable, "-u", str(PROJECT_ROOT / "scripts" / "pipeline.py"),
                    "qa-judge", "--dataset-dir", str(args.dataset_dir),
                    "--group", group, "--input", input_mode, "--qa-model", model,
                    "--thinking-effort", effort,
                    "--video-scope", "all",
                ]
                if group == FAIRY_TALE_GROUP and input_mode == "video":
                    command.append("--with-work-title-prefix")
                if based:
                    command.append("--based")
                for field, value in limits.items():
                    command.extend(("--" + field.replace("_", "-"), str(value)))
                plan.append((f"{model}__{group}__{condition}", command))
    return plan


def display_command(command: list[str]) -> str:
    return subprocess.list2cmdline(command) if os.name == "nt" else shlex.join(command)


STATISTIC_PREFIXES = (
    "QA:", "Judge:", "This run:", "QA output diagnostics (", "Question filter gates:",
)
NO_TARGETS = "No eligible question/video targets in the selected scope."


@dataclass
class JobOutcome:
    returncode: int | None = None
    statistics: list[str] = field(default_factory=list)
    interrupted: bool = False
    no_targets: bool = False
    output_failed: bool = False

    @property
    def status(self) -> str:
        if self.interrupted:
            return "interrupted"
        if self.returncode is None:
            return "launch_failed"
        if self.output_failed:
            return "output_failed"
        if self.returncode:
            reported = any(line.startswith(("QA:", "Judge:", "This run:"))
                           for line in self.statistics)
            return "failed" if reported else "early_failed"
        return "zero_targets" if self.no_targets else "succeeded"


def run_job(command: list[str], outcome: JobOutcome) -> None:
    env = {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}
    process = subprocess.Popen(
        command, cwd=PROJECT_ROOT, env=env, stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace",
        bufsize=1,
    )

    def stream_output() -> None:
        display_output = True
        try:
            for line in process.stdout:
                text = line.strip()
                if text.startswith(STATISTIC_PREFIXES):
                    outcome.statistics.append(text)
                elif text == NO_TARGETS:
                    outcome.no_targets = True
                    outcome.statistics.append(text)
                elif text.startswith("Interrupted: stopping admission;"):
                    outcome.interrupted = True
                if display_output:
                    try:
                        print(line, end="", flush=True)
                    except (OSError, UnicodeError):
                        outcome.output_failed = True
                        display_output = False
        except OSError:
            outcome.output_failed = True

    # Keep draining while the parent waits, including the child's Ctrl+C cleanup.
    reader = threading.Thread(target=stream_output, name="qa-judge-output")
    reader.start()
    try:
        process.wait()
    except KeyboardInterrupt:
        outcome.interrupted = True
        # Ctrl+C also reaches the child in a normal terminal. Allow claim release
        # and final statistics before terminating a child that does not exit.
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()
        reader.join()
        process.stdout.close()
        outcome.returncode = process.returncode
        if outcome.returncode in (130, -2, -1073741510, 3221225786):
            outcome.interrupted = True


def write_job_summary(summary: TextIO, index: int, total: int, name: str,
                      command: list[str], outcome: JobOutcome) -> None:
    model, group, condition = name.split("__", 2)
    summary.write(
        f"\n[{index}/{total}] {name}\nModel: {model}\nGroup: {group}\n"
        f"Condition: {condition}\nCommand: {display_command(command)}\n"
        f"Status: {outcome.status}\n"
        f"Exit code: {outcome.returncode if outcome.returncode is not None else 'not started'}\n"
    )
    for line in outcome.statistics:
        summary.write(line + "\n")
    if not any(line.startswith(("QA:", "Judge:")) for line in outcome.statistics):
        summary.write("Completion statistics: not reported.\n")
    summary.flush()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default="all", choices=("all", *MODELS),
                        type=lambda value: MODEL_ALIASES.get(value, value),
                        help="Default: all (Gemini, Qwen Max, Kimi only); aliases: cosmos, gemma.")
    parser.add_argument("--group", action="append", choices=GROUPS,
                        help="Repeat to select groups; default: all four groups, including math.")
    parser.add_argument("--condition", action="append", choices=tuple(CONDITIONS),
                        help="Repeat to select conditions; default: all four conditions.")
    parser.add_argument("--config", type=Path,
                        default=RUNNER_DIR / "closed_qa_judge_config.json")
    parser.add_argument("--dataset-dir", type=Path, default=Path("dataset/cases"))
    parser.add_argument("--log-dir", type=Path, default=Path("results/run_all"),
                        help="Parent directory for each run's summary.txt.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print commands without credentials, API calls, or file writes.")
    args = parser.parse_args(argv)
    args.dataset_dir = project_path(args.dataset_dir)
    try:
        config = load_config(project_path(args.config))
        plan = build_plan(args, config)
        print(f"Planned qa-judge commands: {len(plan)}", flush=True)
        if args.dry_run:
            for name, command in plan:
                print(f"\n{name}\n{display_command(command)}")
            return 0

        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        run_dir = project_path(args.log_dir) / f"{stamp}_{args.model}_{uuid.uuid4().hex[:8]}"
        run_dir.mkdir(parents=True)
        summary_path = run_dir / "summary.txt"
        print(f"Summary: {summary_path}", flush=True)
        outcomes: list[JobOutcome] = []
        with summary_path.open("w", encoding="utf-8") as summary:
            summary.write(f"Started: {stamp}\nModel selection: {args.model}\nPlanned commands: {len(plan)}\n")
            summary.flush()
            batch_status = "running"
            try:
                for group in dict.fromkeys(args.group or GROUPS):
                    directory = args.dataset_dir / group
                    if not directory.is_dir() or not any(directory.glob("*.json")):
                        raise ValueError(f"Group has no case JSON files: {directory}")
                models = CLOSED_MODELS if args.model == "all" else (args.model,)
                required_keys = {"OPENROUTER_API_KEY"}
                required_keys.update(API_KEYS[model] for model in models if model in API_KEYS)
                missing = sorted(key for key in required_keys if not os.environ.get(key, "").strip())
                if missing:
                    raise ValueError("Missing environment variables: " + ", ".join(missing))
                for index, (name, command) in enumerate(plan, start=1):
                    outcome = JobOutcome()
                    outcomes.append(outcome)
                    print(f"\n[{index}/{len(plan)}] {name}\n{display_command(command)}", flush=True)
                    try:
                        run_job(command, outcome)
                    except KeyboardInterrupt:
                        outcome.interrupted = True
                    except OSError as exc:
                        print(f"Error running {name}: {exc}", file=sys.stderr, flush=True)
                    finally:
                        write_job_summary(summary, index, len(plan), name, command, outcome)
                    if outcome.interrupted:
                        print("\nInterrupted. Valid saved results can be resumed.", file=sys.stderr)
                        break
                    if outcome.status not in ("succeeded", "zero_targets"):
                        print(f"FAILED ({outcome.returncode}): {name}; continuing with remaining jobs.", flush=True)
                if any(outcome.interrupted for outcome in outcomes):
                    batch_status = "interrupted"
                elif any(outcome.status not in ("succeeded", "zero_targets") for outcome in outcomes):
                    batch_status = "failed"
                else:
                    batch_status = "completed"
            except KeyboardInterrupt:
                batch_status = "interrupted"
                raise
            except (OSError, ValueError):
                batch_status = "failed" if outcomes else "preflight_failed"
                raise
            finally:
                successes = sum(outcome.status in ("succeeded", "zero_targets") for outcome in outcomes)
                interrupted = sum(outcome.interrupted for outcome in outcomes)
                failures = len(outcomes) - successes - interrupted
                finished = (f"Finished: {successes} succeeded, {failures} failed, {interrupted} interrupted; "
                            f"{len(plan) - len(outcomes)} not started.")
                summary.write(f"\nBatch status: {batch_status}\n{finished}\n")
                summary.flush()
                print(f"\n{finished}", flush=True)
        return 130 if interrupted else 1 if failures else 0
    except KeyboardInterrupt:
        print("\nInterrupted. Rerun the same command to resume valid saved results.", file=sys.stderr)
        return 130
    except (OSError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
