"""Generate aggregate JSON summaries and presentation-friendly Markdown reports."""

from __future__ import annotations

import argparse
import uuid
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

from .core import atomic_write_json, grouped_dir, iter_case_paths, load_case, utc_now
from .qa import selected_thinking_efforts
from .settings import (
    DEFAULT_MARKDOWN_OUTPUT,
    DEFAULT_SUMMARY_OUTPUT,
    GEMINI_MARKDOWN_OUTPUT,
    GEMINI_QA_MODEL,
    GEMINI_SUMMARY_OUTPUT,
    PROJECT_ROOT,
    QUESTION_TYPES,
    VERDICTS,
)


def aggregate_video_verdict(verdicts: Iterable[str]) -> str:
    observed = set(verdicts)
    if "video_grounded" in observed and "knowledge_trapped" not in observed:
        return "video_grounded"
    if "knowledge_trapped" in observed and "video_grounded" not in observed:
        return "knowledge_trapped"
    return "ambiguous_or_unjudgeable"


def _safe_rate(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 6) if denominator else None


def _summarize(
    answers: dict[str, Counter[str]],
    videos: dict[str, Counter[str]],
) -> dict[str, Any]:
    conflict_answer_base = (
        answers["conflict"]["video_grounded"]
        + answers["conflict"]["knowledge_trapped"]
    )
    conflict_video_base = (
        videos["conflict"]["video_grounded"]
        + videos["conflict"]["knowledge_trapped"]
    )
    control_answers = sum(answers["control"].values())
    control_videos = sum(videos["control"].values())
    return {
        "answers": {
            "conflict": {
                "total": sum(answers["conflict"].values()),
                "labels": {
                    label: answers["conflict"][label] for label in sorted(VERDICTS)
                },
                "trapped_answer_rate": _safe_rate(
                    answers["conflict"]["knowledge_trapped"],
                    conflict_answer_base,
                ),
            },
            "control": {
                "total": control_answers,
                "labels": {
                    label: answers["control"][label] for label in sorted(VERDICTS)
                },
                "grounded_answer_rate": _safe_rate(
                    answers["control"]["video_grounded"], control_answers
                ),
            },
        },
        "videos": {
            "conflict": {
                "total": sum(videos["conflict"].values()),
                "labels": {
                    label: videos["conflict"][label] for label in sorted(VERDICTS)
                },
                "trapped_video_rate": _safe_rate(
                    videos["conflict"]["knowledge_trapped"], conflict_video_base
                ),
            },
            "control": {
                "total": control_videos,
                "labels": {
                    label: videos["control"][label] for label in sorted(VERDICTS)
                },
                "grounded_video_rate": _safe_rate(
                    videos["control"]["video_grounded"], control_videos
                ),
            },
        },
    }


def default_summary_output(
    qa_models: Iterable[str] | None,
    group: str | None = None,
) -> Path:
    output = (
        GEMINI_SUMMARY_OUTPUT
        if set(qa_models or []) == {GEMINI_QA_MODEL}
        else DEFAULT_SUMMARY_OUTPUT
    )
    return grouped_dir(output.parent, group) / output.name


def command_summary(args: argparse.Namespace) -> int:
    selected_models = set(args.qa_model or [])
    selected_efforts = selected_thinking_efforts(args.thinking_effort)
    latest: dict[tuple[Any, ...], tuple[str, str, dict[str, Any]]] = {}
    dataset_dir = grouped_dir(args.dataset_dir, args.group)
    for case_path in iter_case_paths(dataset_dir, args.case_id):
        case = load_case(case_path)
        questions = {item["question_id"]: item for item in case["questions"]}
        for video in case["videos"]:
            for result in video["qa_results"]:
                if selected_models and result.get("model") not in selected_models:
                    continue
                if (
                    selected_efforts is not None
                    and result.get("thinking_effort") not in selected_efforts
                ):
                    continue
                judgment = result.get("judgment")
                if not isinstance(judgment, dict):
                    continue
                question = questions[result["question_id"]]
                key = (
                    case["case_id"],
                    video["video_id"],
                    result["video_sha256"],
                    result["question_id"],
                    result["model"],
                    result.get("thinking_effort"),
                )
                latest[key] = (video["role"], question["question_type"], judgment)

    answer_counts = {"conflict": Counter(), "control": Counter()}
    typed_answers: dict[str, dict[str, Counter[str]]] = defaultdict(
        lambda: {"conflict": Counter(), "control": Counter()}
    )
    grouped_videos: dict[tuple[Any, ...], list[str]] = defaultdict(list)
    typed_grouped_videos: dict[tuple[Any, ...], list[str]] = defaultdict(list)
    for key, (role, question_type, judgment) in latest.items():
        verdict = judgment["verdict"]
        answer_counts[role][verdict] += 1
        typed_answers[question_type][role][verdict] += 1
        grouped_videos[(key[0], key[1], key[2], key[4], key[5], role)].append(
            verdict
        )
        typed_grouped_videos[
            (question_type, key[0], key[1], key[2], key[4], key[5], role)
        ].append(verdict)

    video_counts = {"conflict": Counter(), "control": Counter()}
    typed_videos: dict[str, dict[str, Counter[str]]] = defaultdict(
        lambda: {"conflict": Counter(), "control": Counter()}
    )
    case_counts: dict[str, dict[str, Counter[str]]] = defaultdict(
        lambda: {"conflict": Counter(), "control": Counter()}
    )
    for key, verdicts in grouped_videos.items():
        verdict = aggregate_video_verdict(verdicts)
        case_id, role = key[0], key[-1]
        video_counts[role][verdict] += 1
        case_counts[case_id][role][verdict] += 1
    for key, verdicts in typed_grouped_videos.items():
        typed_videos[key[0]][key[-1]][aggregate_video_verdict(verdicts)] += 1

    overall = _summarize(answer_counts, video_counts)
    report = {
        "generated_at": utc_now(),
        "answers": overall["answers"],
        "videos": overall["videos"],
        "question_types": {
            question_type: _summarize(
                typed_answers[question_type], typed_videos[question_type]
            )
            for question_type in QUESTION_TYPES
            if question_type in typed_answers
        },
        "cases": {
            case_id: {
                role: {
                    "videos": sum(counts[role].values()),
                    "labels": {
                        label: counts[role][label] for label in sorted(VERDICTS)
                    },
                }
                for role in ("conflict", "control")
            }
            for case_id, counts in sorted(case_counts.items())
        },
    }
    output = args.output or default_summary_output(args.qa_model, args.group)
    atomic_write_json(output, report)
    print(f"Wrote summary: {output}")
    return 0


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else "" if value is None else str(value)


def _markdown_value(value: Any) -> str:
    return _text(value).replace("\r\n", "\n").replace("\r", "\n").replace(
        "\n", "<br>"
    )


def _local_video_link(local_path: Any) -> str:
    display = _text(local_path).replace("\\", "/")
    if not display:
        return ""
    supplied = Path(display)
    resolved = supplied if supplied.is_absolute() else PROJECT_ROOT / supplied
    target = f"potplayer://{resolved.resolve(strict=False).as_posix()}"
    label = display.replace("[", r"\[").replace("]", r"\]")
    return f"[{label}]({target})"


def _result_selected(
    result: dict[str, Any],
    models: set[str] | None,
    efforts: set[str | None] | None,
) -> bool:
    return (
        (models is None or result.get("model") in models)
        and (efforts is None or result.get("thinking_effort") in efforts)
    )


def _case_markdown(
    case: dict[str, Any],
    *,
    models: set[str] | None,
    efforts: set[str | None] | None,
) -> list[str]:
    title = _markdown_value(case["title"]).replace("#", r"\#")
    lines = [f"## {title}", ""]
    for index, question in enumerate(case["questions"], start=1):
        lines.extend(
            [
                f"### Question {index}",
                "",
                f"**Question pair:** {_markdown_value(question['question_pair_id'])}",
                "",
                f"**Question type:** {_markdown_value(question['question_type'])}",
                "",
                f"**Question:** {_markdown_value(question['text_en'])}",
                "",
            ]
        )
        for video in case["videos"]:
            lines.extend(
                [
                    f"#### Video `{_markdown_value(video['video_id'])}`",
                    "",
                    f"**Local file:** {_local_video_link(video['local_path'])}",
                    "",
                ]
            )
            results = [
                result
                for result in video["qa_results"]
                if result.get("question_id") == question["question_id"]
                and _result_selected(result, models, efforts)
            ] or [{}]
            for result_index, result in enumerate(results, start=1):
                judgment = result.get("judgment")
                judgment = judgment if isinstance(judgment, dict) else {}
                lines.extend(
                    [
                        f"##### QA result {result_index}",
                        "",
                        f"- **QA model:** {_markdown_value(result.get('model'))}",
                        "- **Thinking effort:** "
                        f"{_markdown_value(result.get('thinking_effort'))}",
                    ]
                )
                if result.get("effective_reasoning_effort") is not None:
                    lines.append(
                        "- **Effective reasoning effort:** "
                        f"{_markdown_value(result['effective_reasoning_effort'])}"
                    )
                lines.extend(
                    [
                        f"- **Answer:** {_markdown_value(result.get('raw_answer'))}",
                        f"- **Verdict:** {_markdown_value(judgment.get('verdict'))}",
                        f"- **Confidence:** {_markdown_value(judgment.get('confidence'))}",
                        "",
                    ]
                )
    return lines


def build_markdown(
    case_paths: list[Path],
    *,
    qa_models: set[str] | None = None,
    thinking_efforts: set[str | None] | None = None,
) -> str:
    lines = ["# Video Knowledge Conflict Results", ""]
    for path in case_paths:
        lines.extend(
            _case_markdown(
                load_case(path), models=qa_models, efforts=thinking_efforts
            )
        )
    return "\n".join(lines).rstrip() + "\n"


def _atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(content, encoding="utf-8", newline="\n")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def default_markdown_output(
    qa_models: Iterable[str] | None,
    group: str | None = None,
) -> Path:
    output = (
        GEMINI_MARKDOWN_OUTPUT
        if set(qa_models or []) == {GEMINI_QA_MODEL}
        else DEFAULT_MARKDOWN_OUTPUT
    )
    return grouped_dir(output.parent, group) / output.name


def command_report(args: argparse.Namespace) -> int:
    dataset_dir = grouped_dir(args.dataset_dir, args.group)
    paths = iter_case_paths(dataset_dir, args.case_id)
    selected_models = set(args.qa_model) if args.qa_model else None
    selected_efforts = selected_thinking_efforts(args.thinking_effort)
    output = args.output or default_markdown_output(args.qa_model, args.group)
    _atomic_write_text(
        output,
        build_markdown(
            paths,
            qa_models=selected_models,
            thinking_efforts=selected_efforts,
        ),
    )
    print(f"Wrote Markdown: {output}")
    return 0
