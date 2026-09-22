"""Generate effort-specific JSON summaries and a combined Markdown report."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

from .core import (
    PipelineError,
    atomic_write_json,
    atomic_write_text,
    canonical_verdict,
    grouped_dir,
    iter_case_paths,
    load_case,
    video_case_context,
    qa_result_input_mode,
    utc_now,
)
from .qa import (
    expand_thinking_efforts,
    get_backend,
    qa_result_thinking_effort,
    qa_result_work_title_prefix,
    work_title_prefix_condition,
)
from .settings import (
    FAIRY_TALE_GROUP,
    PROJECT_ROOT,
    QA_MODEL_SLUGS,
    RESULTS_DIR,
    VERDICTS,
)


def aggregate_video_verdict(verdicts: Iterable[str]) -> str:
    observed = {canonical_verdict(verdict) for verdict in verdicts}
    if "context_grounded" in observed and "knowledge_trapped" not in observed:
        return "context_grounded"
    if "knowledge_trapped" in observed and "context_grounded" not in observed:
        return "knowledge_trapped"
    return "ambiguous_or_unjudgeable"


def _safe_rate(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 6) if denominator else None


def _summarize_counts(
    answers: dict[str, Counter[str]],
    videos: dict[str, Counter[str]],
) -> dict[str, Any]:
    conflict_answers = sum(answers["conflict"].values())
    conflict_videos = sum(videos["conflict"].values())
    control_answers = sum(answers["control"].values())
    control_videos = sum(videos["control"].values())
    return {
        "answers": {
            "conflict": {
                "total": conflict_answers,
                "labels": {
                    label: answers["conflict"][label] for label in sorted(VERDICTS)
                },
                "trapped_answer_rate": _safe_rate(
                    answers["conflict"]["knowledge_trapped"],
                    conflict_answers,
                ),
            },
            "control": {
                "total": control_answers,
                "labels": {
                    label: answers["control"][label] for label in sorted(VERDICTS)
                },
                "grounded_answer_rate": _safe_rate(
                    answers["control"]["context_grounded"], control_answers
                ),
            },
        },
        "videos": {
            "conflict": {
                "total": conflict_videos,
                "labels": {
                    label: videos["conflict"][label] for label in sorted(VERDICTS)
                },
                "trapped_video_rate": _safe_rate(
                    videos["conflict"]["knowledge_trapped"], conflict_videos
                ),
            },
            "control": {
                "total": control_videos,
                "labels": {
                    label: videos["control"][label] for label in sorted(VERDICTS)
                },
                "grounded_video_rate": _safe_rate(
                    videos["control"]["context_grounded"], control_videos
                ),
            },
        },
    }


def _effort_name(effort: str | None) -> str:
    return "none" if effort is None else effort


def _result_matches(
    result: dict[str, Any],
    *,
    qa_model: str,
    input_mode: str,
    efforts: set[str | None],
    work_title_prefix: bool | None,
) -> bool:
    matches = (
        result.get("model") == qa_model
        and qa_result_input_mode(result) == input_mode
        and qa_result_thinking_effort(result) in efforts
    )
    if not matches or input_mode != "video" or work_title_prefix is None:
        return matches
    return qa_result_work_title_prefix(result) is work_title_prefix


def _newer(candidate: dict[str, Any], current: dict[str, Any] | None) -> bool:
    if current is None:
        return True
    return (
        str(candidate.get("timestamp", "")),
        str(candidate.get("run_id", "")),
    ) >= (
        str(current.get("timestamp", "")),
        str(current.get("run_id", "")),
    )


def build_summary(
    case_paths: list[Path],
    *,
    qa_model: str,
    input_mode: str,
    effort: str | None,
    work_title_prefix: bool | None,
) -> dict[str, Any]:
    latest: dict[tuple[str, str, str], tuple[str, dict[str, Any]]] = {}
    for case_path in case_paths:
        case = load_case(case_path)
        for video in case["videos"]:
            for result in video["qa_results"]:
                if not _result_matches(
                    result,
                    qa_model=qa_model,
                    input_mode=input_mode,
                    efforts={effort},
                    work_title_prefix=work_title_prefix,
                ) or not isinstance(result.get("judgment"), dict):
                    continue
                key = (case["case_id"], video["video_id"], result["question_id"])
                previous = latest.get(key)
                if previous is not None and not _newer(result, previous[1]):
                    continue
                judgment = dict(result["judgment"])
                judgment["verdict"] = canonical_verdict(judgment["verdict"])
                latest[key] = (
                    video["role"],
                    {**result, "judgment": judgment},
                )

    answer_counts = {"conflict": Counter(), "control": Counter()}
    grouped_videos: dict[tuple[str, str, str], list[str]] = defaultdict(list)
    for key, (role, result) in latest.items():
        verdict = result["judgment"]["verdict"]
        answer_counts[role][verdict] += 1
        grouped_videos[(key[0], key[1], role)].append(verdict)

    video_counts = {"conflict": Counter(), "control": Counter()}
    case_counts: dict[str, dict[str, Counter[str]]] = defaultdict(
        lambda: {"conflict": Counter(), "control": Counter()}
    )
    for (case_id, _, role), verdicts in grouped_videos.items():
        verdict = aggregate_video_verdict(verdicts)
        video_counts[role][verdict] += 1
        case_counts[case_id][role][verdict] += 1
    overall = _summarize_counts(answer_counts, video_counts)
    summary = {
        "generated_at": utc_now(),
        "qa_model": qa_model,
        "input": input_mode,
        "thinking_effort": _effort_name(effort),
        "answers": overall["answers"],
        "videos": overall["videos"],
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
    if work_title_prefix is not None:
        summary["work_title_prefix"] = work_title_prefix
    return summary


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


def _latest_results(
    results: Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    latest: dict[str | None, dict[str, Any]] = {}
    for result in results:
        effort = qa_result_thinking_effort(result)
        if _newer(result, latest.get(effort)):
            latest[effort] = result
    return [latest[key] for key in sorted(latest, key=lambda value: str(value))]


def build_markdown(
    case_paths: list[Path],
    *,
    qa_model: str,
    input_mode: str,
    efforts: set[str | None],
    work_title_prefix: bool | None,
) -> str:
    effort_names = ", ".join(
        _effort_name(item) for item in sorted(efforts, key=str)
    )
    lines = [
        f"# {input_mode.title()} Knowledge Conflict Results",
        "",
        f"**QA model:** {_markdown_value(qa_model)}",
        "",
        f"**Thinking efforts:** {effort_names}",
        "",
    ]
    if work_title_prefix is not None:
        prefix_name = "with_prefix" if work_title_prefix else "no_prefix"
        lines.extend([f"**Work-title prefix:** {prefix_name}", ""])
    for path in case_paths:
        case = load_case(path)
        title = _markdown_value(case["title"]).replace("#", r"\#")
        lines.extend([f"## {title}", ""])
        question_groups = []
        for video in case["videos"]:
            for question in video_case_context(case, video)["questions"]:
                group = next((item for item in question_groups if item[0] == question), None)
                if group is None:
                    group = (question, [])
                    question_groups.append(group)
                group[1].append(video)
        for index, (question, question_videos) in enumerate(question_groups, start=1):
            lines.extend(
                [
                    f"### Question {index}",
                    "",
                    f"**Question:** {_markdown_value(question['text_en'])}",
                    "",
                ]
            )
            for video in question_videos:
                matching = _latest_results(
                    result
                    for result in video["qa_results"]
                    if result.get("question_id") == question["question_id"]
                    and _result_matches(
                        result,
                        qa_model=qa_model,
                        input_mode=input_mode,
                        efforts=efforts,
                        work_title_prefix=work_title_prefix,
                    )
                )
                if input_mode == "description" and not matching:
                    continue
                lines.extend([f"#### Video `{video['video_id']}`", ""])
                if input_mode == "description":
                    lines.extend(
                        [
                            "**Context:** "
                            f"{_markdown_value(matching[-1].get('context_text_en'))}",
                            "",
                        ]
                    )
                else:
                    lines.extend(
                        [f"**Local file:** {_local_video_link(video['local_path'])}", ""]
                    )
                for result_index, result in enumerate(matching or [{}], start=1):
                    judgment = result.get("judgment")
                    judgment = judgment if isinstance(judgment, dict) else {}
                    verdict = canonical_verdict(judgment.get("verdict", ""))
                    effort_display = (
                        _effort_name(qa_result_thinking_effort(result))
                        if result
                        else ""
                    )
                    lines.extend(
                        [
                            f"##### QA result {result_index}",
                            "",
                            f"- **QA model:** {_markdown_value(result.get('model'))}",
                            f"- **Thinking effort:** {effort_display}",
                        ]
                    )
                    if result.get("effective_reasoning_effort") is not None:
                        lines.append(
                            "- **Effective reasoning effort:** "
                            f"{_markdown_value(result['effective_reasoning_effort'])}"
                        )
                    lines.extend(
                        [
                            f"- **Raw answer:** {_markdown_value(result.get('raw_answer'))}",
                            "- **Final answer (judged):** "
                            f"{_markdown_value(result.get('final_answer'))}",
                            f"- **Verdict:** {_markdown_value(verdict)}",
                            f"- **Confidence:** {_markdown_value(judgment.get('confidence'))}",
                            "",
                        ]
                    )
    return "\n".join(lines).rstrip() + "\n"


def _discover_efforts(
    case_paths: list[Path],
    *,
    qa_model: str,
    input_mode: str,
    work_title_prefix: bool | None,
) -> tuple[str | None, ...]:
    backend = get_backend(qa_model)
    observed: set[str | None] = set()
    for path in case_paths:
        case = load_case(path)
        for video in case["videos"]:
            for result in video["qa_results"]:
                effort = qa_result_thinking_effort(result)
                if (
                    _result_matches(
                        result,
                        qa_model=qa_model,
                        input_mode=input_mode,
                        efforts=set(backend.thinking_efforts),
                        work_title_prefix=work_title_prefix,
                    )
                    and isinstance(result.get("judgment"), dict)
                    and effort in backend.thinking_efforts
                ):
                    observed.add(effort)
    selected = tuple(
        effort for effort in backend.thinking_efforts if effort in observed
    )
    return selected or (backend.default_thinking_effort,)


def _require_video_prefix_metadata(
    case_paths: list[Path],
    *,
    qa_model: str,
) -> None:
    for path in case_paths:
        case = load_case(path)
        for video in case["videos"]:
            for result in video["qa_results"]:
                if (
                    result.get("model") == qa_model
                    and qa_result_input_mode(result) == "video"
                    and qa_result_work_title_prefix(result) is None
                ):
                    raise PipelineError(
                        f"QA result {case['case_id']}/{video['video_id']}/"
                        f"{result['question_id']} in {path} has no "
                        "work_title_prefix. Backfill it with true or false before "
                        "summarizing video results."
                    )


def _fairy_video_prefix_name(args: argparse.Namespace) -> str | None:
    if args.input != "video" or args.group != FAIRY_TALE_GROUP:
        return None
    return "with_prefix" if args.with_work_title_prefix else "no_prefix"


def command_summarize(args: argparse.Namespace) -> int:
    dataset_dir = grouped_dir(args.dataset_dir, args.group)
    paths = iter_case_paths(dataset_dir, args.case_id)
    work_title_prefix = work_title_prefix_condition(
        args.group,
        args.input,
        args.with_work_title_prefix,
    )
    if work_title_prefix is not None:
        _require_video_prefix_metadata(paths, qa_model=args.qa_model)
    requested = list(args.thinking_effort or [])
    efforts = (
        expand_thinking_efforts(requested, args.qa_model)
        if requested and "all" not in requested
        else _discover_efforts(
            paths,
            qa_model=args.qa_model,
            input_mode=args.input,
            work_title_prefix=work_title_prefix,
        )
    )
    result_dir = grouped_dir(RESULTS_DIR, args.group)
    model_slug = QA_MODEL_SLUGS[args.qa_model]
    prefix_name = _fairy_video_prefix_name(args)
    for effort in efforts:
        output_parts = [model_slug, args.input]
        if prefix_name is not None:
            output_parts.append(prefix_name)
        output_parts.extend([_effort_name(effort), "summary"])
        output = result_dir / ("_".join(output_parts) + ".json")
        atomic_write_json(
            output,
            build_summary(
                paths,
                qa_model=args.qa_model,
                input_mode=args.input,
                effort=effort,
                work_title_prefix=work_title_prefix,
            ),
        )
        print(f"Wrote summary: {output}")

    report_parts = [model_slug, args.input]
    if prefix_name is not None:
        report_parts.append(prefix_name)
    report_output = result_dir / ("_".join(report_parts) + "_report.md")
    atomic_write_text(
        report_output,
        build_markdown(
            paths,
            qa_model=args.qa_model,
            input_mode=args.input,
            efforts=set(efforts),
            work_title_prefix=work_title_prefix,
        ),
    )
    print(f"Wrote report: {report_output}")
    return 0
