"""QA/Judge selection, force pre-clearing and completion accounting."""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from .common import PipelineError, conflict_question_scopes, question_only_records, video_case_context
from .filters import question_filter_state
from .integrity import judgment_is_current, qa_is_current, require_writable_case, video_selected
from .paths import grouped_dir, iter_case_paths
from .result_rules import (
    FILTER_RESULT_FIELDS,
    qa_result_matches,
    qa_result_work_title_prefix,
    work_title_prefix_condition,
)
from .selection import eligible_videos, selected_questions
from .storage import atomic_write_json, load_case


def selected_targets(case, *, args, efforts):
    """Use the same role and effective questions for every execution phase."""
    question_ids = set(args.question_id or [])
    if args.input == "question_only":
        targets = list(conflict_question_scopes(case))
        selected_questions({**case, 'questions': [q for _, q in targets]}, question_ids)
        for video, question in targets:
            if question_ids and question['question_id'] not in question_ids:
                continue
            for effort in efforts:
                yield video, question, effort
        return
    for video in eligible_videos(case, input_mode=args.input,
                                 selected_video_ids=set(args.video_id or [])):
        for question in selected_questions(video_case_context(case, video), question_ids):
            for effort in efforts:
                yield video, question, effort


def _result_base_selected(video, result, *, args, efforts):
    return (
        video_selected(video, args.input)
        and (not args.video_id or video["video_id"] in args.video_id)
        and (not args.question_id or result.get("question_id") in args.question_id)
        and qa_result_matches(result, input_selection=args.input, model=args.qa_model,
                              efforts=efforts, based=args.based)
    )


def result_selected(video, result, *, args, efforts):
    prefix = work_title_prefix_condition(args.group, args.input, args.with_work_title_prefix)
    return (_result_base_selected(video, result, args=args, efforts=efforts)
            and (prefix is None or qa_result_work_title_prefix(result) is prefix))


def _legacy_video_result_selected(video, result, *, args, efforts):
    return (
        work_title_prefix_condition(args.group, args.input, args.with_work_title_prefix) is not None
        and _result_base_selected(video, result, args=args, efforts=efforts)
        and qa_result_work_title_prefix(result) is None
    )


def _question_result_selected(question, result, *, args, efforts):
    return (result.get("question_id") == question["question_id"]
            and qa_result_matches(result, input_selection="question_only",
                                  model=args.qa_model, efforts=efforts))


def target_results(case, video, question, effort, *, args):
    """Current records for one target; question-only has one authoritative result."""
    if args.input == 'question_only':
        state = question_filter_state(case, video, question, args.qa_model, effort)
        return [state['result']] if state['status'] in ('unjudged', 'passed', 'failed') else []
    return [result for result in video['qa_results']
            if result.get('question_id') == question['question_id']
            and result_selected(video, result, args=args, efforts={effort})
            and qa_is_current(case, video, result)]


def preflight_cases(
    args: argparse.Namespace,
    efforts: tuple[str | None, ...],
    *,
    snapshot: list[tuple[Path, dict[str, Any]]] | None = None,
) -> tuple[list[tuple[Path, dict[str, Any]]], int]:
    dataset_dir = grouped_dir(args.dataset_dir, args.group)
    loaded = []
    target_total = 0
    source = snapshot if snapshot is not None else (
        (path, load_case(path)) for path in iter_case_paths(dataset_dir, args.case_id))
    for path, case in source:
        require_writable_case(case, path)
        target_total += sum(1 for _ in selected_targets(case, args=args, efforts=efforts))
        loaded.append((path, case))
    return loaded, target_total


def _selected_video_results(case, *, args, efforts):
    for video, question, effort in selected_targets(case, args=args, efforts=efforts):
        for result in video['qa_results']:
            if result.get('question_id') == question['question_id']:
                yield video, result, effort


def require_selected_final_answers(loaded, *, args, efforts):
    for path, case in loaded:
        for video, question, effort in selected_targets(case, args=args, efforts=efforts):
            results = (question_only_records(question) if args.input == 'question_only'
                       else target_results(case, video, question, effort, args=args))
            for result in results:
                if args.input == 'question_only' and not _question_result_selected(
                        question, result, args=args, efforts={effort}):
                    continue
                final_answer = result.get('final_answer')
                if isinstance(final_answer, str) and final_answer.strip():
                    continue
                owner = video['video_id'] if video is not None else 'case'
                raise PipelineError(
                    f"Selected QA result {case['case_id']}/{owner}/{question['question_id']} "
                    f"in {path} has no final_answer. Run qa-judge with --force-qa "
                    "to replace old-format QA results."
                )


def require_selected_prefix_metadata(loaded, *, args, efforts):
    if work_title_prefix_condition(args.group, args.input, args.with_work_title_prefix) is None:
        return
    for path, case in loaded:
        for video, result, effort in _selected_video_results(case, args=args, efforts=efforts):
            if _legacy_video_result_selected(video, result, args=args, efforts={effort}):
                raise PipelineError(
                    f"Selected QA result {case['case_id']}/{video['video_id']}/"
                    f"{result['question_id']} in {path} has no work_title_prefix. "
                    "Backfill it with true or false, or run qa-judge with --force-qa "
                    "to replace the unclassified result."
                )


def preclear_force(loaded, *, args, efforts):
    qa_cleared = 0
    judgments_cleared = 0
    changed = []
    for path, case in loaded:
        case_changed = False
        for video, question, effort in selected_targets(case, args=args, efforts=efforts):
            fields = ('question_only_results', *FILTER_RESULT_FIELDS) if args.input == 'question_only' else ('qa_results',)
            owner = question if args.input == 'question_only' else video
            for field in fields:
                results = owner.get(field, [])
                kept = []
                for result in results:
                    selected = (_question_result_selected(question, result, args=args, efforts={effort})
                                if args.input == 'question_only' else (
                                    result.get('question_id') == question['question_id']
                                    and (result_selected(video, result, args=args, efforts={effort})
                                         or (args.force_qa and _legacy_video_result_selected(
                                             video, result, args=args, efforts={effort})))))
                    if selected and args.force_qa:
                        qa_cleared += 1
                        case_changed = True
                        continue
                    if selected and args.force_judge and result.get('judgment') is not None:
                        result['judgment'] = None
                        judgments_cleared += 1
                        case_changed = True
                    kept.append(result)
                if kept or video is not None:
                    owner[field] = kept
                else:
                    owner.pop(field, None)
        if case_changed:
            changed.append((path, case))

    # Validate every target before this global write phase; no provider calls
    # can occur until every planned clear has been persisted.
    for path, case in changed:
        atomic_write_json(path, case)
    if args.force_qa:
        print(f"Cleared {qa_cleared} QA result(s) before forced QA.")
    elif args.force_judge:
        print(f"Cleared {judgments_cleared} judgment(s) before forced judging.")


def _completion_from_loaded(loaded, *, args, efforts):
    qa_completed = qa_total = judge_completed = judge_total = 0
    for _, case in loaded:
        for video, question, effort in selected_targets(case, args=args, efforts=efforts):
            qa_total += 1
            results = target_results(case, video, question, effort, args=args)
            qa_completed += bool(results)
            judge_total += len(results)
            judge_completed += sum(
                question_filter_state(case, video, question, args.qa_model, effort)['status'] in ('passed', 'failed')
                if args.input == 'question_only' else judgment_is_current(case, video, result)
                for result in results)
    return qa_completed, qa_total, judge_completed, judge_total


def completion_counts(args, efforts, *, snapshot=None):
    loaded, _ = preflight_cases(args, efforts, snapshot=snapshot)
    return _completion_from_loaded(loaded, args=args, efforts=efforts)


def qa_completed_from_loaded(loaded, *, args, efforts):
    return _completion_from_loaded(loaded, args=args, efforts=efforts)[0]
