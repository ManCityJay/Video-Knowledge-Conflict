"""Argument parsing and dispatch for the unified pipeline entry point."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from .authoring import command_author, command_judge, command_questions
from .core import PipelineError, command_split_source, validate_group
from .generation import command_generate, command_review
from .qa import REQUEST_TIMEOUT_SECONDS, command_qa
from .reporting import command_report, command_summary
from .settings import (
    ARK_BASE_URL,
    CLI_THINKING_EFFORTS,
    DEFAULT_CASE_DIR,
    DEFAULT_CASE_WORKERS,
    DEFAULT_QA_MODEL,
    DEFAULT_REQUEST_RPM,
    DEFAULT_REQUEST_WORKERS,
    DEFAULT_SEEDANCE_TOTAL_WORKERS,
    DEFAULT_SOURCE_CASE_DIR,
    PROJECT_ROOT,
    QA_MODELS,
    SEEDANCE_MODEL,
)


def _stage(subparsers: Any, name: str) -> argparse.ArgumentParser:
    return subparsers.add_parser(name, add_help=False)


def _group_name(value: str) -> str:
    try:
        return validate_group(value)
    except PipelineError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def _add_group(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--group", type=_group_name)


def _add_case_selection(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--dataset-dir", type=Path, default=DEFAULT_CASE_DIR)
    parser.add_argument("--case-id", action="append")
    _add_group(parser)


def _add_case_workers(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--case-workers", type=int, default=DEFAULT_CASE_WORKERS)


def _add_request_limits(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--openrouter-workers", type=int, default=DEFAULT_REQUEST_WORKERS
    )
    parser.add_argument("--openrouter-rpm", type=float, default=DEFAULT_REQUEST_RPM)


def _add_retries(parser: argparse.ArgumentParser, *, timeout: int = 900) -> None:
    parser.add_argument("--max-retries", type=int, default=4)
    parser.add_argument("--timeout", type=int, default=timeout)


def _add_result_filters(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--qa-model", action="append", choices=QA_MODELS)
    parser.add_argument(
        "--thinking-effort",
        action="append",
        choices=(*CLI_THINKING_EFFORTS, "all"),
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(add_help=False)
    subparsers = parser.add_subparsers(dest="command", required=True)

    split_source = _stage(subparsers, "split-source")
    split_source.add_argument("--source-md", required=True, type=Path)
    split_source.add_argument("--output-dir", type=Path, default=DEFAULT_SOURCE_CASE_DIR)
    _add_group(split_source)
    split_source.add_argument("--force", action="store_true")
    split_source.set_defaults(func=command_split_source)

    author = _stage(subparsers, "author")
    author.add_argument("--source-dir", type=Path, default=DEFAULT_SOURCE_CASE_DIR)
    author.add_argument("--output-dir", type=Path, default=DEFAULT_CASE_DIR)
    author.add_argument("--case-id", action="append")
    _add_group(author)
    _add_case_workers(author)
    _add_request_limits(author)
    author.add_argument("--max-repairs", type=int, default=2)
    _add_retries(author)
    author.add_argument("--force", action="store_true")
    author.set_defaults(func=command_author)

    questions = _stage(subparsers, "questions")
    _add_case_selection(questions)
    _add_case_workers(questions)
    _add_request_limits(questions)
    questions.add_argument("--max-repairs", type=int, default=2)
    _add_retries(questions)
    questions.add_argument("--force", action="store_true")
    questions.set_defaults(func=command_questions)

    generate = _stage(subparsers, "generate")
    _add_case_selection(generate)
    _add_case_workers(generate)
    generate.add_argument("--video-id", action="append")
    generate.add_argument("--retry-failed", action="store_true")
    generate.add_argument("--seedance-workers", type=int, default=3)
    generate.add_argument(
        "--seedance-total-workers", type=int, default=DEFAULT_SEEDANCE_TOTAL_WORKERS
    )
    generate.add_argument(
        "--model", default=os.environ.get("SEEDANCE_MODEL", SEEDANCE_MODEL)
    )
    generate.add_argument(
        "--base-url", default=os.environ.get("ARK_BASE_URL", ARK_BASE_URL)
    )
    generate.add_argument("--ratio", default="adaptive")
    generate.add_argument("--resolution", default="720p")
    generate.add_argument("--duration", type=int, default=-1)
    generate.add_argument("--poll-interval", type=int, default=30)
    generate.add_argument("--max-polls", type=int, default=120)
    generate.set_defaults(func=command_generate)

    review = _stage(subparsers, "review")
    review.add_argument("--dataset-dir", type=Path, default=DEFAULT_CASE_DIR)
    review.add_argument("--case-id", required=True)
    review.add_argument("--video-id", required=True)
    review.add_argument("--decision", required=True, choices=("verified", "rejected"))
    _add_group(review)
    review.set_defaults(func=command_review)

    qa = _stage(subparsers, "qa")
    _add_case_selection(qa)
    qa.add_argument("--video-id", action="append")
    qa.add_argument("--question-id", action="append")
    qa.add_argument("--qa-model", choices=QA_MODELS, default=DEFAULT_QA_MODEL)
    _add_case_workers(qa)
    _add_request_limits(qa)
    qa.add_argument(
        "--thinking-effort",
        action="append",
        choices=(*CLI_THINKING_EFFORTS, "all"),
    )
    qa.add_argument("--qa-workers", type=int, default=3)
    _add_retries(qa, timeout=REQUEST_TIMEOUT_SECONDS)
    qa.add_argument("--force", action="store_true")
    qa.set_defaults(func=command_qa)

    judge = _stage(subparsers, "judge")
    _add_case_selection(judge)
    judge.add_argument("--video-id", action="append")
    judge.add_argument("--question-id", action="append")
    _add_result_filters(judge)
    _add_case_workers(judge)
    _add_request_limits(judge)
    _add_retries(judge)
    judge.add_argument("--force", action="store_true")
    judge.set_defaults(func=command_judge)

    summary = _stage(subparsers, "summary")
    _add_case_selection(summary)
    _add_result_filters(summary)
    summary.add_argument("--output", type=Path)
    summary.set_defaults(func=command_summary)

    report = _stage(subparsers, "report")
    _add_case_selection(report)
    _add_result_filters(report)
    report.add_argument("--output", type=Path)
    report.set_defaults(func=command_report)

    all_stages = _stage(subparsers, "all")
    all_stages.add_argument("--source-dir", type=Path, default=DEFAULT_SOURCE_CASE_DIR)
    all_stages.add_argument("--dataset-dir", type=Path, default=DEFAULT_CASE_DIR)
    all_stages.add_argument("--case-id", action="append")
    _add_group(all_stages)
    _add_case_workers(all_stages)
    _add_request_limits(all_stages)
    all_stages.add_argument("--seedance-workers", type=int, default=3)
    all_stages.add_argument(
        "--seedance-total-workers", type=int, default=DEFAULT_SEEDANCE_TOTAL_WORKERS
    )
    all_stages.add_argument("--qa-workers", type=int, default=2)
    all_stages.add_argument("--qa-model", choices=QA_MODELS, default=DEFAULT_QA_MODEL)
    all_stages.add_argument(
        "--thinking-effort",
        action="append",
        choices=(*CLI_THINKING_EFFORTS, "all"),
    )
    all_stages.set_defaults(func=command_all)
    return parser


def _repeated(flag: str, values: list[str] | None) -> list[str]:
    return [item for value in values or [] for item in (flag, value)]


def command_all(args: argparse.Namespace) -> int:
    """Run author, questions, generate, QA, and judge in isolated processes."""
    entry = Path(__file__).resolve().parent.parent / "pipeline.py"
    cases = _repeated("--case-id", args.case_id)
    efforts = _repeated("--thinking-effort", args.thinking_effort)
    group = ["--group", args.group] if args.group else []
    request_limits = [
        "--case-workers",
        str(args.case_workers),
        "--openrouter-workers",
        str(args.openrouter_workers),
        "--openrouter-rpm",
        str(args.openrouter_rpm),
    ]
    stages = (
        (
            "author",
            [
                "author",
                "--source-dir",
                str(args.source_dir),
                "--output-dir",
                str(args.dataset_dir),
                *cases,
                *group,
                *request_limits,
            ],
        ),
        (
            "questions",
            [
                "questions",
                "--dataset-dir",
                str(args.dataset_dir),
                *cases,
                *group,
                *request_limits,
            ],
        ),
        (
            "generate",
            [
                "generate",
                "--dataset-dir",
                str(args.dataset_dir),
                *cases,
                *group,
                "--case-workers",
                str(args.case_workers),
                "--seedance-workers",
                str(args.seedance_workers),
                "--seedance-total-workers",
                str(args.seedance_total_workers),
            ],
        ),
        (
            "qa",
            [
                "qa",
                "--dataset-dir",
                str(args.dataset_dir),
                *cases,
                *group,
                *request_limits,
                "--qa-workers",
                str(args.qa_workers),
                "--qa-model",
                args.qa_model,
                *efforts,
            ],
        ),
        (
            "judge",
            [
                "judge",
                "--dataset-dir",
                str(args.dataset_dir),
                *cases,
                *group,
                *request_limits,
                "--qa-model",
                args.qa_model,
                *efforts,
            ],
        ),
    )
    for name, stage_args in stages:
        print(f"\n===== {name} =====", flush=True)
        completed = subprocess.run(
            [sys.executable, str(entry), *stage_args],
            cwd=PROJECT_ROOT,
            check=False,
        )
        if completed.returncode:
            print(
                f"Stage {name} failed with exit code {completed.returncode}.",
                file=sys.stderr,
            )
            return completed.returncode
    return 0


def _validate(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    for field in (
        "case_workers",
        "openrouter_workers",
        "seedance_workers",
        "seedance_total_workers",
        "qa_workers",
    ):
        if hasattr(args, field) and getattr(args, field) <= 0:
            parser.error(f"--{field.replace('_', '-')} must be greater than zero")
    if hasattr(args, "openrouter_rpm") and args.openrouter_rpm < 0:
        parser.error("--openrouter-rpm must not be negative")
    for field in ("max_repairs", "max_retries"):
        if hasattr(args, field) and getattr(args, field) < 0:
            parser.error(f"--{field.replace('_', '-')} must not be negative")
    if hasattr(args, "timeout") and args.timeout <= 0:
        parser.error("--timeout must be greater than zero")
    if hasattr(args, "poll_interval") and args.poll_interval < 0:
        parser.error("--poll-interval must not be negative")
    if hasattr(args, "max_polls") and args.max_polls <= 0:
        parser.error("--max-polls must be greater than zero")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    arguments = list(sys.argv[1:] if argv is None else argv)
    forbidden = [value for value in arguments if value in ("-h", "--help")]
    if forbidden:
        parser.error(f"unrecognized arguments: {' '.join(forbidden)}")
    args = parser.parse_args(arguments)
    _validate(args, parser)
    try:
        return int(args.func(args))
    except PipelineError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
