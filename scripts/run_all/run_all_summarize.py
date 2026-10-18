#!/usr/bin/env python3
"""Discover saved conflict QA experiments and summarize all valid judged results."""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

from run_qa_judge import CONDITIONS, GROUPS, MODELS, MODEL_ALIASES, display_command, project_path
from vconflict_pipeline.common import PipelineError, utc_now
from vconflict_pipeline.result_rules import (
    expand_thinking_efforts,
    qa_result_based,
    qa_result_input_mode,
    qa_result_thinking_effort,
    qa_result_work_title_prefix,
    work_title_prefix_condition,
)
from vconflict_pipeline.settings import CLI_QA_MODEL_IDS, PROJECT_ROOT, QA_MODEL_SLUGS, RESULTS_DIR
from vconflict_pipeline.storage import atomic_write_json, atomic_write_text, read_json


OUTPUT_DIR = RESULTS_DIR / "run_all"


@dataclass(frozen=True)
class Experiment:
    model: str
    group: str
    condition: str
    efforts: tuple[str | None, ...]

    @property
    def input_mode(self) -> str:
        return CONDITIONS[self.condition][0]

    @property
    def based(self) -> bool:
        return CONDITIONS[self.condition][1]

    @property
    def prefix(self) -> bool | None:
        return work_title_prefix_condition(self.group, self.input_mode, True)

    @property
    def qa_model(self) -> str:
        return CLI_QA_MODEL_IDS[self.model]

    def identity(self) -> dict:
        return {"model": self.model, "qa_model": self.qa_model, "group": self.group,
                "condition": self.condition, "input": self.input_mode,
                "based": self.based, "prefix": self.prefix, "filter": "all"}

    def command(self, args: argparse.Namespace) -> list[str]:
        command = [sys.executable, "-u", str(PROJECT_ROOT / "scripts" / "pipeline.py"),
                   "summarize", "--dataset-dir", str(args.dataset_dir),
                   "--qa-model", self.model, "--group", self.group,
                   "--input", self.input_mode,
                   "--summary-workers", str(args.summary_workers)]
        for effort in self.efforts:
            command.extend(("--thinking-effort", "none" if effort is None else effort))
        if self.based:
            command.append("--based")
        if self.prefix:
            command.append("--with-work-title-prefix")
        return command


def discover(args: argparse.Namespace) -> tuple[list[Experiment], list[dict]]:
    model_names = {CLI_QA_MODEL_IDS[model]: model for model in args.models}
    supported = {model: expand_thinking_efforts(["all"], CLI_QA_MODEL_IDS[model])
                 for model in args.models}
    observed = defaultdict(set)
    failures = []
    for group in args.groups:
        paths = sorted((args.dataset_dir / group).glob("*.json"))
        if not paths:
            print(f"No case JSON files in group: {group}", flush=True)
        for path in paths:
            try:
                # Discover historical targets before applying freshness, judgment,
                # ready-state or filter checks; the native summarizer owns those.
                case = read_json(path)
                videos = case.get("videos", [])
                if not isinstance(videos, list):
                    raise PipelineError(f"{path}: videos must be a list")
                for video in videos:
                    if not isinstance(video, dict):
                        raise PipelineError(f"{path}: video must be an object")
                    if video.get("role") != "conflict":
                        continue
                    results = video.get("qa_results", [])
                    if not isinstance(results, list):
                        raise PipelineError(f"{path}: qa_results must be a list")
                    for result in results:
                        if not isinstance(result, dict):
                            raise PipelineError(f"{path}: QA result must be an object")
                        stored_model = result.get("model")
                        model = model_names.get(stored_model) if isinstance(stored_model, str) else None
                        if model is None:
                            continue
                        mode = qa_result_input_mode(result)
                        if mode not in ("video", "description"):
                            continue
                        condition = mode + ("-based" if qa_result_based(result) else "")
                        if condition not in args.conditions:
                            continue
                        prefix = work_title_prefix_condition(group, mode, True)
                        if prefix is True and qa_result_work_title_prefix(result) is not True:
                            continue
                        effort = qa_result_thinking_effort(result)
                        if effort in supported[model]:
                            observed[model, group, condition].add(effort)
            except PipelineError as exc:
                failures.append({"phase": "discovery", "group": group,
                                 "case_path": str(path), "error": str(exc)})
                print(f"Discovery failed: {exc}", file=sys.stderr, flush=True)
    experiments = []
    for model in args.models:
        for group in args.groups:
            for condition in args.conditions:
                efforts = tuple(effort for effort in supported[model]
                                if effort in observed[model, group, condition])
                if efforts:
                    experiments.append(Experiment(model, group, condition, efforts))
    return experiments, failures


def collect_reports(experiment: Experiment, stdout: str) -> list[dict]:
    """Read only output paths announced by this successful native invocation."""
    summary_paths = []
    report_paths = []
    for line in stdout.splitlines():
        if line.startswith("Wrote summary: "):
            summary_paths.append(project_path(Path(line.removeprefix("Wrote summary: ").strip())))
        elif line.startswith("Wrote report: "):
            report_paths.append(project_path(Path(line.removeprefix("Wrote report: ").strip())))
    if (len(summary_paths) != len(experiment.efforts)
            or len(set(summary_paths)) != len(summary_paths) or len(report_paths) != 1):
        raise PipelineError("Native summarize did not announce all expected JSON/Markdown reports")
    parent = (RESULTS_DIR / experiment.group / QA_MODEL_SLUGS[experiment.qa_model]).resolve()
    report_path = report_paths[0]
    for path in [*summary_paths, report_path]:
        if path.parent != parent or not path.is_file():
            raise PipelineError(f"Unexpected or missing native report: {path}")
    if report_path.suffix != ".md":
        raise PipelineError(f"Expected a native Markdown report: {report_path}")
    expected = {"none" if effort is None else effort for effort in experiment.efforts}
    records = {}
    for path in summary_paths:
        if path.suffix != ".json":
            raise PipelineError(f"Expected a native JSON summary: {path}")
        summary = read_json(path)
        effort = summary.get("thinking_effort")
        if (effort not in expected or effort in records
                or summary.get("qa_model") != experiment.qa_model
                or summary.get("input") != experiment.input_mode
                or summary.get("based") is not experiment.based
                or summary.get("work_title_prefix") is not experiment.prefix
                or summary.get("filter") != "all"):
            raise PipelineError(f"Native summary metadata does not match this experiment: {path}")
        conflict = summary.get("answers", {}).get("conflict")
        if (not isinstance(conflict, dict)
                or not {"total", "labels", "grounded_answer_rate", "trapped_answer_rate"}.issubset(conflict)
                or not isinstance(conflict["labels"], dict)
                or not {"context_grounded", "knowledge_trapped", "ambiguous_or_unjudgeable"}
                .issubset(conflict["labels"])):
            raise PipelineError(f"Native summary has no complete answers.conflict: {path}")
        records[effort] = {
            **experiment.identity(), "effort": effort,
            "native_summary_path": path.relative_to(PROJECT_ROOT).as_posix(),
            "native_report_path": report_path.relative_to(PROJECT_ROOT).as_posix(),
            "conflict": conflict,
        }
    return [records["none" if effort is None else effort] for effort in experiment.efforts]


def markdown_cell(value: object) -> str:
    if value is None:
        return "null"
    return str(value).replace("|", r"\|").replace("\r", " ").replace("\n", "<br>")


def native_link(label: str, relative_path: str) -> str:
    path = os.path.relpath(PROJECT_ROOT / relative_path, OUTPUT_DIR).replace("\\", "/")
    return f"[{label}]({quote(path, safe='/._-')})"


def build_report(summary: dict) -> str:
    lines = ["# 批量实验汇总（filter=all）", "",
             f"生成时间：{summary['generated_at']}", "",
             f"数据目录：`{summary['dataset_dir']}`", "",
             "只展示保存过 conflict 目标 QA 的实验。指标原样取自原生汇总的 "
             "`answers.conflict`，统计全部有效已判定目标，包含 ambiguous，不依赖 question-only；"
             "不跨实验合并计数或平均比例。", "",
             f"发现 {summary['discovered_experiments']} 个实验组合，成功 {summary['successful_experiments']} 个，"
             f"生成 {len(summary['experiments'])} 条 effort 记录；"
             f"跳过 {summary['skipped_combinations']} 个未发现目标 QA 的组合。", ""]
    if summary["experiments"]:
        lines.extend([
            "| Model | Group | Input | Based | Prefix | Effort | total | grounded | trapped | ambiguous | grounded_answer_rate | trapped_answer_rate | 原生报告 |",
            "|---|---|---|---|---|---|---:|---:|---:|---:|---:|---:|---|",
        ])
        for record in summary["experiments"]:
            conflict = record["conflict"]
            labels = conflict["labels"]
            values = [record["model"], record["group"], record["input"],
                      str(record["based"]).lower(),
                      "n/a" if record["prefix"] is None else str(record["prefix"]).lower(),
                      record["effort"], conflict["total"], labels["context_grounded"],
                      labels["knowledge_trapped"], labels["ambiguous_or_unjudgeable"],
                      conflict["grounded_answer_rate"], conflict["trapped_answer_rate"]]
            links = native_link("JSON", record["native_summary_path"]) + " / " + native_link(
                "Markdown", record["native_report_path"])
            lines.append("| " + " | ".join(markdown_cell(value) for value in values) + f" | {links} |")
    elif not summary["discovered_experiments"]:
        lines.append("未发现任何符合所选范围的 conflict 目标 QA 记录，汇总为空。")
    else:
        lines.append("发现的实验均未成功生成本次报告，汇总为空；失败任务未使用旧报告替代。")
    if summary["failures"]:
        lines.extend(["", "## 失败信息", ""])
        for failure in summary["failures"]:
            identity = "/".join(str(failure[key]) for key in ("model", "group", "condition", "case_path")
                                if key in failure)
            lines.append(f"- {markdown_cell(identity)} ({failure['phase']}): "
                         f"{markdown_cell(failure['error'])}")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default="all", choices=("all", *MODELS),
                        type=lambda value: MODEL_ALIASES.get(value, value),
                        help="all includes all seven cloud/local models; aliases: cosmos, gemma.")
    parser.add_argument("--group", action="append", choices=GROUPS)
    parser.add_argument("--condition", action="append", choices=tuple(CONDITIONS))
    parser.add_argument("--dataset-dir", type=Path, default=Path("dataset/cases"))
    parser.add_argument("--summary-workers", type=int, default=4)
    parser.add_argument("--dry-run", action="store_true",
                        help="Discover and print commands without API calls or report writes.")
    args = parser.parse_args()
    if args.summary_workers <= 0:
        parser.error("--summary-workers must be greater than zero")
    args.dataset_dir = project_path(args.dataset_dir)
    args.models = MODELS if args.model == "all" else (args.model,)
    args.groups = tuple(dict.fromkeys(args.group or GROUPS))
    args.conditions = tuple(dict.fromkeys(args.condition or CONDITIONS))
    try:
        if not args.dataset_dir.is_dir():
            raise PipelineError(f"Dataset directory was not found: {args.dataset_dir}")
        experiments, failures = discover(args)
        print(f"Discovered experiments: {len(experiments)}; effort records: "
              f"{sum(len(experiment.efforts) for experiment in experiments)}", flush=True)
        if args.dry_run:
            for experiment in experiments:
                print(display_command(experiment.command(args)), flush=True)
            if not experiments:
                print("No saved conflict QA experiments match the selection.")
            return 1 if failures else 0

        records = []
        succeeded = 0
        env = {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}
        for index, experiment in enumerate(experiments, start=1):
            command = experiment.command(args)
            print(f"\n[{index}/{len(experiments)}] {display_command(command)}", flush=True)
            phase = "summarize"
            try:
                result = subprocess.run(command, cwd=PROJECT_ROOT, env=env, capture_output=True,
                                        text=True, encoding="utf-8", errors="replace", check=False)
                print(result.stdout, end="", flush=True)
                print(result.stderr, end="", file=sys.stderr, flush=True)
                if result.returncode:
                    error = result.stderr.strip() or result.stdout.strip() or "Native summarize failed"
                    failures.append({**experiment.identity(), "phase": phase,
                                     "returncode": result.returncode, "error": error})
                    continue
                phase = "collect_reports"
                current = collect_reports(experiment, result.stdout)
                records.extend(current)
                succeeded += 1
            except (PipelineError, OSError, ValueError, KeyError, TypeError) as exc:
                failures.append({**experiment.identity(), "phase": phase, "error": str(exc)})
                print(f"Failed: {exc}; continuing.", file=sys.stderr, flush=True)
        summary = {
            "generated_at": utc_now(), "dataset_dir": str(args.dataset_dir), "filter": "all",
            "selection": {"models": list(args.models), "groups": list(args.groups),
                          "conditions": list(args.conditions)},
            "discovered_experiments": len(experiments), "successful_experiments": succeeded,
            "skipped_combinations": len(args.models) * len(args.groups) * len(args.conditions) - len(experiments),
            "experiments": records, "failures": failures,
        }
        report = build_report(summary)
        atomic_write_json(OUTPUT_DIR / "summary.json", summary)
        atomic_write_text(OUTPUT_DIR / "report.md", report)
        print(f"\nWrote batch summary: {OUTPUT_DIR / 'summary.json'}")
        print(f"Wrote batch report: {OUTPUT_DIR / 'report.md'}")
        print(f"Finished: {succeeded} experiments succeeded, {len(failures)} failures.")
        return 1 if failures else 0
    except (PipelineError, OSError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nInterrupted. Rerun to rebuild the selected reports.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
