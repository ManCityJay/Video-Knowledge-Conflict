"""QA/Judge selection, force pre-clearing and completion accounting."""

from __future__ import annotations

from .integrity import qa_is_current, judgment_is_current, require_writable_case
from .filters import effective_prefix, qa_allowed

import argparse
from pathlib import Path
from typing import Any
from .selection import eligible_videos, selected_questions, target_video_selected

from .core import (
    PipelineError, atomic_write_json, grouped_dir, iter_case_paths, load_case,
    video_case_context, qa_result_input_mode, require_question_only_compatible,
)
from .qa import (
    qa_result_based, qa_result_key, qa_result_thinking_effort,
    qa_result_work_title_prefix, qa_run_key, work_title_prefix_condition,
)

JUDGE_SYSTEM_PROMPT = """Evaluate the supplied final_answer against the context
references. Treat final_answer as the complete answer to judge. Do not infer,
reconstruct, or consider any reasoning or other response text that is not in
final_answer.

For video_role=conflict:
- context_grounded means final_answer clearly reports the conflict-context fact.
- knowledge_trapped means final_answer substitutes the normal-control answer for the
  conflict-context fact.
- ambiguous_or_unjudgeable covers irrelevant, unresolved, mixed, contradictory,
  hedged, or otherwise unclassifiable final answers.

For video_role=control:
- context_grounded means final_answer clearly reports the normal-control fact.
- never use knowledge_trapped; an answer matching the conflict reference or
  neither reference is ambiguous_or_unjudgeable.

Return only the requested structured result."""


def _result_base_selected(
    video: dict[str, Any],
    result: dict[str, Any],
    *,
    args: argparse.Namespace,
    efforts: set[str | None],
) -> bool:
    return not (
        not target_video_selected(video, args.input, getattr(args, "video_scope", None),
                                  based=bool(getattr(args, "based", False)))
        or (args.video_id and video["video_id"] not in set(args.video_id))
        or (args.question_id and result["question_id"] not in set(args.question_id))
        or result.get("model") != args.qa_model
        or qa_result_input_mode(result) != args.input
        or qa_result_thinking_effort(result) not in efforts
    )


def _result_selected(
    video: dict[str, Any],
    result: dict[str, Any],
    *,
    args: argparse.Namespace,
    efforts: set[str | None],
) -> bool:
    if not _result_base_selected(video, result, args=args, efforts=efforts):
        return False
    if qa_result_based(result) is not bool(getattr(args, "based", False)):
        return False
    prefix_condition = work_title_prefix_condition(
        args.group,
        args.input,
        args.with_work_title_prefix,
    )
    return (
        prefix_condition is None
        or qa_result_work_title_prefix(result) is prefix_condition
    )


def _legacy_video_result_selected(
    video: dict[str, Any],
    result: dict[str, Any],
    *,
    args: argparse.Namespace,
    efforts: set[str | None],
) -> bool:
    prefix_condition = work_title_prefix_condition(
        args.group,
        args.input,
        args.with_work_title_prefix,
    )
    return (
        prefix_condition is not None
        and _result_base_selected(video, result, args=args, efforts=efforts)
        and qa_result_based(result) is bool(getattr(args, "based", False))
        and qa_result_work_title_prefix(result) is None
    )


def _question_result_selected(
    question: dict[str, Any],
    result: dict[str, Any],
    *,
    args: argparse.Namespace,
    efforts: set[str | None],
) -> bool:
    return not (
        (args.question_id and question["question_id"] not in set(args.question_id))
        or result.get("question_id") != question["question_id"]
        or result.get("model") != args.qa_model
        or qa_result_input_mode(result) != "question_only"
        or qa_result_thinking_effort(result) not in efforts
    )


def _preflight_cases(
    args: argparse.Namespace,
    efforts: tuple[str | None, ...],
    *, enforce_gate: bool = True, include_control: bool = True,
    snapshot: list[tuple[Path, dict[str, Any]]] | None = None,
) -> tuple[list[tuple[Path, dict[str, Any]]], int]:
    dataset_dir = grouped_dir(args.dataset_dir, args.group)
    selected_question_ids = set(args.question_id or [])
    selected_videos = set(args.video_id or [])
    loaded: list[tuple[Path, dict[str, Any]]] = []
    target_total = 0
    source = snapshot if snapshot is not None else (
        (path, load_case(path)) for path in iter_case_paths(dataset_dir, args.case_id))
    for path, case in source:
        require_writable_case(case, path)
        if args.input == "question_only":
            questions = selected_questions(
                {**case, "questions": require_question_only_compatible(case)},
                selected_question_ids,
            )
            target_total += len(questions) * len(efforts)
            loaded.append((path, case))
            continue
        videos = eligible_videos(
            case,
            input_mode=args.input,
            selected_video_ids=selected_videos,
            video_scope=getattr(args, "video_scope", None),
            based=bool(getattr(args, "based", False)),
        )
        for video in videos:
            if not include_control and video["role"] == "control":
                continue
            questions = selected_questions(video_case_context(case, video), selected_question_ids)
            target_total += sum(
                not enforce_gate or qa_allowed(case, video, question, args.qa_model, effort,
                    effective_prefix(args.group, args.with_work_title_prefix), args.input)
                for question in questions for effort in efforts)
        loaded.append((path, case))
    return loaded, target_total


def _gate_result(case, video, result, args):
    if not target_video_selected(video, args.input, getattr(args, "video_scope", None),
                                 based=bool(getattr(args, "based", False))):
        return False
    question = next((q for q in video_case_context(case, video)['questions']
                     if q['question_id'] == result.get('question_id')), None)
    return question is not None and qa_allowed(
        case, video, question, args.qa_model, qa_result_thinking_effort(result),
        effective_prefix(args.group, args.with_work_title_prefix), args.input)


def _require_selected_final_answers(
    loaded: list[tuple[Path, dict[str, Any]]],
    *,
    args: argparse.Namespace,
    efforts: set[str | None],
) -> None:
    for path, case in loaded:
        if args.input == "question_only":
            for question in require_question_only_compatible(case):
                for result in question.get("question_only_results", []):
                    if not _question_result_selected(
                        question, result, args=args, efforts=efforts
                    ):
                        continue
                    final_answer = result.get("final_answer")
                    if isinstance(final_answer, str) and final_answer.strip():
                        continue
                    raise PipelineError(
                        f"Selected QA result {case['case_id']}/"
                        f"{question['question_id']} in {path} has no final_answer. "
                        "Run qa-judge with --force-qa to replace old-format QA "
                        "results."
                    )
            continue
        for video in case["videos"]:
            for result in video["qa_results"]:
                if not _gate_result(case, video, result, args):
                    continue
                if not qa_is_current(case, video, result):
                    continue
                if not _result_selected(
                    video, result, args=args, efforts=efforts
                ):
                    continue
                final_answer = result.get("final_answer")
                if isinstance(final_answer, str) and final_answer.strip():
                    continue
                raise PipelineError(
                    f"Selected QA result {case['case_id']}/{video['video_id']}/"
                    f"{result['question_id']} in {path} has no final_answer. "
                    "Run qa-judge with --force-qa to replace old-format QA results."
                )


def _require_selected_prefix_metadata(
    loaded: list[tuple[Path, dict[str, Any]]],
    *,
    args: argparse.Namespace,
    efforts: set[str | None],
) -> None:
    if work_title_prefix_condition(
        args.group,
        args.input,
        args.with_work_title_prefix,
    ) is None:
        return
    for path, case in loaded:
        for video in case["videos"]:
            for result in video["qa_results"]:
                if not _gate_result(case, video, result, args):
                    continue
                if not _legacy_video_result_selected(
                    video, result, args=args, efforts=efforts
                ):
                    continue
                raise PipelineError(
                    f"Selected QA result {case['case_id']}/{video['video_id']}/"
                    f"{result['question_id']} in {path} has no "
                    "work_title_prefix. Backfill it with true or false, or run "
                    "qa-judge with --force-qa to replace the unclassified result."
                )


def _preclear_force(
    loaded: list[tuple[Path, dict[str, Any]]],
    *,
    args: argparse.Namespace,
    efforts: set[str | None],
) -> None:
    qa_cleared = 0
    judgments_cleared = 0
    changed: list[tuple[Path, dict[str, Any]]] = []

    for path, case in loaded:
        case_changed = False
        if args.input == "question_only":
            for question in require_question_only_compatible(case):
                results = question.get("question_only_results", [])
                if args.force_qa:
                    kept = []
                    for result in results:
                        if _question_result_selected(
                            question, result, args=args, efforts=efforts
                        ):
                            qa_cleared += 1
                            case_changed = True
                        else:
                            kept.append(result)
                    if kept:
                        question["question_only_results"] = kept
                    else:
                        question.pop("question_only_results", None)
                elif args.force_judge:
                    for result in results:
                        if not _question_result_selected(
                            question, result, args=args, efforts=efforts
                        ) or result.get("judgment") is None:
                            continue
                        result["judgment"] = None
                        judgments_cleared += 1
                        case_changed = True
            if case_changed:
                changed.append((path, case))
            continue
        for video in case["videos"]:
            if args.input == "video" and video["role"] == "control":
                # Filters are forced only by --filter-only; do not invalidate
                # the admission decision between filter checks and conflict QA.
                continue
            if args.force_qa:
                kept: list[dict[str, Any]] = []
                for result in video["qa_results"]:
                    if not _gate_result(case, video, result, args):
                        kept.append(result)
                        continue
                    if _result_selected(
                        video, result, args=args, efforts=efforts
                    ) or _legacy_video_result_selected(
                        video, result, args=args, efforts=efforts
                    ):
                        qa_cleared += 1
                        case_changed = True
                    else:
                        kept.append(result)
                video["qa_results"] = kept
            elif args.force_judge:
                for result in video["qa_results"]:
                    if not _gate_result(case, video, result, args):
                        continue
                    if not _result_selected(
                        video, result, args=args, efforts=efforts
                    ) or result.get("judgment") is None:
                        continue
                    result["judgment"] = None
                    judgments_cleared += 1
                    case_changed = True
        if case_changed:
            changed.append((path, case))

    # This is deliberately a separate global phase. No provider call can occur
    # until every selected case has been validated and every planned clear has
    # been persisted.
    for path, case in changed:
        atomic_write_json(path, case)

    if args.force_qa:
        print(f"Cleared {qa_cleared} QA result(s) before forced QA.")
    elif args.force_judge:
        print(
            f"Cleared {judgments_cleared} judgment(s) before forced judging."
        )


def _find_question(case: dict[str, Any], question_id: str) -> dict[str, Any]:
    for question in case["questions"]:
        if question["question_id"] == question_id:
            return question
    raise PipelineError(
        f"Question {question_id} was not found in case {case['case_id']}."
    )


def _completion_counts(
    args: argparse.Namespace,
    efforts: tuple[str | None, ...],
    *, include_control: bool = True,
    snapshot: list[tuple[Path, dict[str, Any]]] | None = None,
) -> tuple[int, int, int, int]:
    loaded, qa_total = _preflight_cases(args, efforts, include_control=include_control, snapshot=snapshot)
    qa_completed = _qa_completed_from_loaded(
        loaded, args=args, efforts=efforts, include_control=include_control,
    )
    effort_set = set(efforts)
    judge_total = 0
    judge_completed = 0

    for _, case in loaded:
        if args.input == "question_only":
            for question in require_question_only_compatible(case):
                for result in question.get("question_only_results", []):
                    if not _question_result_selected(
                        question, result, args=args, efforts=effort_set
                    ):
                        continue
                    judge_total += 1
                    judge_completed += isinstance(result.get("judgment"), dict)
            continue
        for video in case["videos"]:
            if not include_control and video["role"] == "control":
                continue
            for result in video["qa_results"]:
                if not _gate_result(case, video, result, args):
                    continue
                if not _result_selected(
                    video, result, args=args, efforts=effort_set
                ):
                    continue
                if not qa_is_current(case, video, result):
                    continue
                judge_total += 1
                judge_completed += judgment_is_current(case, video, result)
    return qa_completed, qa_total, judge_completed, judge_total


def _qa_completed_from_loaded(
    loaded: list[tuple[Path, dict[str, Any]]],
    *,
    args: argparse.Namespace,
    efforts: tuple[str | None, ...],
    include_control: bool = True,
) -> int:
    selected_question_ids = set(args.question_id or [])
    selected_videos = set(args.video_id or [])
    prefix_condition = work_title_prefix_condition(
        args.group,
        args.input,
        args.with_work_title_prefix,
    )
    completed = 0
    for _, case in loaded:
        if args.input == "question_only":
            questions = selected_questions(
                {**case, "questions": require_question_only_compatible(case)},
                selected_question_ids,
            )
            for question in questions:
                existing = {
                    qa_result_key(result)
                    for result in question.get("question_only_results", [])
                }
                completed += sum(
                    qa_run_key(
                        "question_only",
                        question["question_id"],
                        args.qa_model,
                        effort,
                    )
                    in existing
                    for effort in efforts
                )
            continue
        videos = eligible_videos(
            case,
            input_mode=args.input,
            selected_video_ids=selected_videos,
            video_scope=getattr(args, "video_scope", None),
            based=bool(getattr(args, "based", False)),
        )
        for video in videos:
            if not include_control and video["role"] == "control":
                continue
            questions = selected_questions(video_case_context(case, video), selected_question_ids)
            existing = {
                qa_result_key(
                    result,
                    include_work_title_prefix=prefix_condition is not None,
                )
                for result in video["qa_results"]
                if qa_is_current(case, video, result)
            }
            completed += sum(
                qa_run_key(
                    args.input,
                    question["question_id"],
                    args.qa_model,
                    effort,
                    based=bool(getattr(args, "based", False)),
                    work_title_prefix=prefix_condition,
                )
                in existing
                for effort in efforts
                for question in questions
                if qa_allowed(case, video, question, args.qa_model, effort,
                              effective_prefix(args.group, args.with_work_title_prefix), args.input)
            )
    return completed


def command_qa_judge(args: argparse.Namespace) -> int:
    """Compatibility entry for callers importing the former stage orchestrator."""
    from .scheduler import command_qa_judge as run
    return run(args)
