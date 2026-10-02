"""Execution target selection; historical report selection remains independent."""
from __future__ import annotations

from typing import Any

from .core import PipelineError, resolve_video_path
from .evidence import observed_summary
from .integrity import description_is_current, video_selected


def target_video_selected(
    video: dict[str, Any], input_mode: str, video_scope: str | None = None,
    *, based: bool = False,
) -> bool:
    """Based control answers are historical only, never execution targets."""
    if based and input_mode == "video" and video["role"] == "control":
        return False
    return video_selected(video, input_mode, video_scope)


def selected_questions(
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


def eligible_videos(
    case: dict[str, Any],
    *,
    input_mode: str,
    selected_video_ids: set[str],
    video_scope: str | None = None,
    based: bool = False,
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
        if based and input_mode == "video" and video["role"] == "control":
            if video["video_id"] in selected_video_ids:
                raise PipelineError(
                    f"Control video {case['case_id']}/{video['video_id']} cannot be "
                    "a --based target. Use --input video --filter-only without "
                    "--based to run its original control filter."
                )
            continue
        if not target_video_selected(video, input_mode, video_scope, based=based):
            if video["video_id"] in selected_video_ids:
                raise PipelineError(f"Selected video {video['video_id']} is outside the evaluation scope or not ready.")
            continue
        if input_mode == "description":
            description = video.get("description")
            if not isinstance(description, dict):
                raise PipelineError(
                    f"Context is missing for {case['case_id']}/{video['video_id']}. "
                    "Run description first."
                )
            if not description_is_current(video):
                raise PipelineError(
                    f"Context is stale for {case['case_id']}/{video['video_id']}. "
                    "Run description again."
                )
        else:
            if video["status"] != "ready":
                continue
            observed_summary(video)  # Blocks stale annotations after regeneration.
            resolve_video_path(video["local_path"], must_exist=True)
        eligible.append(video)
    return eligible


