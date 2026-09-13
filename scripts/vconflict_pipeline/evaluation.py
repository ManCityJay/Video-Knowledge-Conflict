"""Combined QA and judgment execution with global force pre-clearing."""

from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from .core import (
    JUDGMENT_SCHEMA,
    PipelineError,
    atomic_write_json,
    grouped_dir,
    iter_case_paths,
    load_case,
    qa_result_input_mode,
    require_nonempty_string,
    resolve_video_path,
    sha256_text,
    utc_now,
)
from .qa import (
    command_qa,
    expand_thinking_efforts,
    preflight_qa_backend,
    qa_result_key,
    qa_result_thinking_effort,
)
from .settings import AUTHOR_JUDGE_MODEL
from .transport import (
    make_openrouter_limiter,
    openrouter_json,
    require_openrouter_api_key,
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


def _selected_questions(
    case: dict[str, Any], selected_question_ids: set[str]
) -> list[dict[str, Any]]:
    if not case["questions"]:
        raise PipelineError(
            f"Case {case['case_id']} has no questions. Run questions first."
        )
    questions = [
        question
        for question in case["questions"]
        if not selected_question_ids
        or question["question_id"] in selected_question_ids
    ]
    missing = selected_question_ids - {
        question["question_id"] for question in questions
    }
    if missing:
        raise PipelineError(
            f"Question IDs not found in {case['case_id']}: "
            f"{', '.join(sorted(missing))}"
        )
    return questions


def _eligible_videos(
    case: dict[str, Any],
    *,
    input_mode: str,
    selected_video_ids: set[str],
) -> list[dict[str, Any]]:
    candidates = [
        video
        for video in case["videos"]
        if input_mode == "video" or video["role"] == "conflict"
    ]
    available = {video["video_id"] for video in candidates}
    missing = selected_video_ids - available
    if missing:
        kind = "Conflict video IDs" if input_mode == "description" else "Video IDs"
        raise PipelineError(
            f"{kind} not found in {case['case_id']}: {', '.join(sorted(missing))}"
        )

    eligible: list[dict[str, Any]] = []
    for video in candidates:
        if selected_video_ids and video["video_id"] not in selected_video_ids:
            continue
        if input_mode == "description":
            description = video.get("description")
            if not isinstance(description, dict):
                raise PipelineError(
                    f"Context is missing for {case['case_id']}/{video['video_id']}. "
                    "Run description first."
                )
            if description.get("source_sha256") != sha256_text(
                video["seedance_prompt_en"]
            ):
                raise PipelineError(
                    f"Context is stale for {case['case_id']}/{video['video_id']}. "
                    "Run description again."
                )
        else:
            if video["status"] != "ready":
                continue
            resolve_video_path(video["local_path"], must_exist=True)
        eligible.append(video)
    return eligible


def _result_selected(
    video: dict[str, Any],
    result: dict[str, Any],
    *,
    args: argparse.Namespace,
    efforts: set[str | None],
) -> bool:
    return not (
        (args.video_id and video["video_id"] not in set(args.video_id))
        or (args.question_id and result["question_id"] not in set(args.question_id))
        or result.get("model") != args.qa_model
        or qa_result_input_mode(result) != args.input
        or qa_result_thinking_effort(result) not in efforts
    )


def _preflight_cases(
    args: argparse.Namespace,
    efforts: tuple[str | None, ...],
) -> tuple[list[tuple[Path, dict[str, Any]]], int]:
    dataset_dir = grouped_dir(args.dataset_dir, args.group)
    selected_questions = set(args.question_id or [])
    selected_videos = set(args.video_id or [])
    loaded: list[tuple[Path, dict[str, Any]]] = []
    target_total = 0
    for path in iter_case_paths(dataset_dir, args.case_id):
        case = load_case(path)
        questions = _selected_questions(case, selected_questions)
        videos = _eligible_videos(
            case,
            input_mode=args.input,
            selected_video_ids=selected_videos,
        )
        target_total += len(questions) * len(videos) * len(efforts)
        loaded.append((path, case))
    return loaded, target_total


def _require_selected_final_answers(
    loaded: list[tuple[Path, dict[str, Any]]],
    *,
    args: argparse.Namespace,
    efforts: set[str | None],
) -> None:
    for path, case in loaded:
        for video in case["videos"]:
            for result in video["qa_results"]:
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
        for video in case["videos"]:
            if args.force_qa:
                kept: list[dict[str, Any]] = []
                for result in video["qa_results"]:
                    if _result_selected(video, result, args=args, efforts=efforts):
                        qa_cleared += 1
                        case_changed = True
                    else:
                        kept.append(result)
                video["qa_results"] = kept
            elif args.force_judge:
                for result in video["qa_results"]:
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


def command_judge(args: argparse.Namespace) -> int:
    api_key = require_openrouter_api_key()
    request_limiter = make_openrouter_limiter(args)
    efforts = set(expand_thinking_efforts(args.thinking_effort, args.qa_model))
    dataset_dir = grouped_dir(args.dataset_dir, args.group)
    case_paths = iter_case_paths(dataset_dir, args.case_id)
    completed = 0
    failures = 0

    def run_case(case_path: Path) -> tuple[int, int]:
        case = load_case(case_path)
        case_completed = 0
        case_failures = 0
        for video in case["videos"]:
            for qa_result in video["qa_results"]:
                if not _result_selected(
                    video, qa_result, args=args, efforts=efforts
                ) or qa_result.get("judgment") is not None:
                    continue
                try:
                    question = _find_question(case, qa_result["question_id"])
                    final_answer = require_nonempty_string(
                        qa_result.get("final_answer"), "final_answer"
                    )
                    judge_input = {
                        "video_role": video["role"],
                        "question": question["text_en"],
                        "final_answer": final_answer,
                        "normal_fact": case["conflict_spec"]["normal_fact_en"],
                        "intended_video_fact": case["conflict_spec"][
                            "intended_video_fact_en"
                        ],
                        "conflict_video_reference": question[
                            "conflict_video_reference_en"
                        ],
                        "normal_control_reference": question[
                            "normal_control_reference_en"
                        ],
                    }
                    result, response = openrouter_json(
                        messages=[
                            {"role": "system", "content": JUDGE_SYSTEM_PROMPT},
                            {
                                "role": "user",
                                "content": json.dumps(
                                    judge_input, ensure_ascii=False
                                ),
                            },
                        ],
                        model=AUTHOR_JUDGE_MODEL,
                        schema_name="knowledge_conflict_judgment",
                        schema=JUDGMENT_SCHEMA,
                        api_key=api_key,
                        timeout=args.timeout,
                        max_retries=args.max_retries,
                        request_limiter=request_limiter,
                    )
                    if video["role"] == "control" and result.get(
                        "verdict"
                    ) == "knowledge_trapped":
                        raise PipelineError(
                            "Luna Pro returned knowledge_trapped for a control video."
                        )
                    qa_result["judgment"] = {
                        "timestamp": utc_now(),
                        "verdict": result["verdict"],
                        "confidence": float(result["confidence"]),
                        "judge_model": AUTHOR_JUDGE_MODEL,
                        "judge_request_id": response.get("id"),
                    }
                    atomic_write_json(case_path, case)
                    case_completed += 1
                    print(
                        f"Judged {case['case_id']}/{video['video_id']}/"
                        f"{question['question_id']}: {result['verdict']}"
                    )
                except PipelineError as exc:
                    case_failures += 1
                    print(
                        f"Error judging {case['case_id']}/{video['video_id']}/"
                        f"{qa_result['question_id']}: {exc}",
                        file=sys.stderr,
                    )
        return case_completed, case_failures

    workers = min(args.case_workers, len(case_paths))
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(run_case, path): path for path in case_paths}
        for future in as_completed(futures):
            case_path = futures[future]
            try:
                done, failed = future.result()
            except PipelineError as exc:
                failures += 1
                print(f"Error judging case {case_path.stem}: {exc}", file=sys.stderr)
                continue
            completed += done
            failures += failed
    print(f"Wrote {completed} judgment(s) into case JSON files.")
    return 1 if failures else 0


def _completion_counts(
    args: argparse.Namespace,
    efforts: tuple[str | None, ...],
) -> tuple[int, int, int, int]:
    loaded, qa_total = _preflight_cases(args, efforts)
    qa_completed = _qa_completed_from_loaded(loaded, args=args, efforts=efforts)
    effort_set = set(efforts)
    judge_total = 0
    judge_completed = 0

    for _, case in loaded:
        for video in case["videos"]:
            for result in video["qa_results"]:
                if not _result_selected(
                    video, result, args=args, efforts=effort_set
                ):
                    continue
                judge_total += 1
                judge_completed += isinstance(result.get("judgment"), dict)
    return qa_completed, qa_total, judge_completed, judge_total


def _qa_completed_from_loaded(
    loaded: list[tuple[Path, dict[str, Any]]],
    *,
    args: argparse.Namespace,
    efforts: tuple[str | None, ...],
) -> int:
    selected_questions = set(args.question_id or [])
    selected_videos = set(args.video_id or [])
    completed = 0
    for _, case in loaded:
        questions = _selected_questions(case, selected_questions)
        videos = _eligible_videos(
            case,
            input_mode=args.input,
            selected_video_ids=selected_videos,
        )
        for video in videos:
            existing = {qa_result_key(result) for result in video["qa_results"]}
            completed += sum(
                (
                    args.input,
                    question["question_id"],
                    args.qa_model,
                    effort,
                )
                in existing
                for effort in efforts
                for question in questions
            )
    return completed


def command_qa_judge(args: argparse.Namespace) -> int:
    # All dependency, credential, selection, file, and context checks happen
    # before force mode is allowed to clear persisted results.
    efforts = expand_thinking_efforts(args.thinking_effort, args.qa_model)
    loaded, qa_total = _preflight_cases(args, efforts)
    if not args.force_qa:
        _require_selected_final_answers(
            loaded,
            args=args,
            efforts=set(efforts),
        )
    qa_done = _qa_completed_from_loaded(loaded, args=args, efforts=efforts)
    qa_needed = qa_total > 0 and (args.force_qa or qa_done != qa_total)
    if qa_needed:
        preflight_qa_backend(args)
    require_openrouter_api_key()
    if args.force_qa or args.force_judge:
        _preclear_force(loaded, args=args, efforts=set(efforts))

    qa_status = command_qa(args) if qa_needed else 0
    judge_status = command_judge(args)
    qa_done, qa_total, judge_done, judge_total = _completion_counts(args, efforts)
    print(f"QA: {qa_done}/{qa_total}")
    print(f"Judge: {judge_done}/{judge_total}")
    incomplete = qa_done != qa_total or judge_done != judge_total
    return 1 if qa_status or judge_status or incomplete else 0
