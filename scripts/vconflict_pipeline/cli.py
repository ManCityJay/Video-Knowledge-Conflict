"""Argument parsing and dispatch for the unified pipeline entry point."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any

from .authoring import command_author, command_questions
from .core import PipelineError, validate_group, validate_id
from .deletion import command_delete
from .descriptions import command_description
from .evaluation import command_qa_judge
from .generation import command_generate, command_review
from .qa import REQUEST_TIMEOUT_SECONDS
from .reporting import command_summarize
from .settings import (
    ARK_BASE_URL,
    CLI_QA_MODEL_IDS,
    CLI_QA_MODELS,
    CLI_THINKING_EFFORTS,
    DEFAULT_CASE_DIR,
    DEFAULT_CASE_WORKERS,
    DEFAULT_QA_MODEL,
    DEFAULT_REQUEST_RPM,
    DEFAULT_REQUEST_WORKERS,
    DEFAULT_SEEDANCE_TOTAL_WORKERS,
    DEFAULT_SOURCE_CASE_DIR,
    FAIRY_TALE_GROUP,
    SEEDANCE_MODEL,
)


def _stage(subparsers: Any, name: str) -> argparse.ArgumentParser:
    return subparsers.add_parser(name, add_help=False)


def _group_name(value: str) -> str:
    try:
        return validate_group(value)
    except PipelineError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def _entity_id(value: str) -> str:
    try:
        return validate_id(value, "ID")
    except PipelineError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def _qa_model(value: str) -> str:
    try:
        return CLI_QA_MODEL_IDS[value]
    except KeyError as exc:
        choices = ", ".join(CLI_QA_MODELS)
        raise argparse.ArgumentTypeError(
            f"invalid QA model: {value!r} (choose from {choices})"
        ) from exc


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


def _add_input(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--input",
        choices=("video", "description", "question_only"),
        default="video",
    )


def _add_thinking_effort(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--thinking-effort",
        action="append",
        choices=(*CLI_THINKING_EFFORTS, "all"),
    )


def _add_work_title_prefix(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--with-work-title-prefix", action="store_true")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(add_help=False)
    subparsers = parser.add_subparsers(dest="command", required=True)

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

    description = _stage(subparsers, "description")
    _add_case_selection(description)
    _add_case_workers(description)
    _add_request_limits(description)
    description.add_argument("--video-id", action="append")
    _add_retries(description)
    description.add_argument("--force", action="store_true")
    description.set_defaults(func=command_description)

    generate = _stage(subparsers, "generate")
    _add_case_selection(generate)
    _add_case_workers(generate)
    generate.add_argument("--video-id", action="append")
    generate.add_argument("--retry-failed", action="store_true")
    generate.add_argument("--regenerate", action="store_true")
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
    generate.add_argument("--duration", type=int, default=5)
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

    delete = _stage(subparsers, "delete")
    delete.add_argument("--dataset-dir", type=Path, default=DEFAULT_CASE_DIR)
    delete.add_argument("--case-id", action="append", type=_entity_id, required=True)
    delete.add_argument("--video-id", action="append", type=_entity_id)
    delete.add_argument("--question-id", action="append", type=_entity_id)
    delete.add_argument("--all", action="store_true", dest="delete_all")
    _add_group(delete)
    delete.set_defaults(func=command_delete)

    qa_judge = _stage(subparsers, "qa-judge")
    _add_case_selection(qa_judge)
    qa_judge.add_argument("--video-id", action="append")
    qa_judge.add_argument("--question-id", action="append")
    qa_judge.add_argument(
        "--qa-model",
        type=_qa_model,
        default=DEFAULT_QA_MODEL,
        metavar="{gemini,qwen3.8-max,kimi-k3}",
    )
    _add_input(qa_judge)
    _add_case_workers(qa_judge)
    _add_request_limits(qa_judge)
    _add_thinking_effort(qa_judge)
    _add_work_title_prefix(qa_judge)
    qa_judge.add_argument("--qa-workers", type=int, default=3)
    _add_retries(qa_judge, timeout=REQUEST_TIMEOUT_SECONDS)
    force = qa_judge.add_mutually_exclusive_group()
    force.add_argument("--force-qa", action="store_true")
    force.add_argument("--force-judge", action="store_true")
    qa_judge.set_defaults(func=command_qa_judge)

    summarize = _stage(subparsers, "summarize")
    _add_case_selection(summarize)
    summarize.add_argument(
        "--qa-model",
        type=_qa_model,
        required=True,
        metavar="{gemini,qwen3.8-max,kimi-k3}",
    )
    _add_input(summarize)
    _add_thinking_effort(summarize)
    _add_work_title_prefix(summarize)
    summarize.set_defaults(func=command_summarize)
    return parser


def _validate(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    if (
        args.command == "qa-judge"
        and args.input == "question_only"
        and args.video_id
    ):
        parser.error("--video-id cannot be combined with --input question_only")
    if getattr(args, "with_work_title_prefix", False):
        if args.group != FAIRY_TALE_GROUP:
            parser.error(
                "--with-work-title-prefix requires "
                f"--group {FAIRY_TALE_GROUP}"
            )
        if args.input != "video":
            parser.error("--with-work-title-prefix requires --input video")
    if args.command == "delete":
        has_selected_items = bool(args.video_id or args.question_id)
        if args.delete_all and has_selected_items:
            parser.error(
                "delete --all cannot be combined with --video-id or --question-id"
            )
        if not args.delete_all:
            if len(args.case_id) != 1:
                parser.error(
                    "deleting videos or questions requires --case-id exactly once"
                )
            if not has_selected_items:
                parser.error("delete requires --video-id, --question-id, or --all")
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
