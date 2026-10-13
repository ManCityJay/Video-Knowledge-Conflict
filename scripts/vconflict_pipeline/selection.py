"""Role-specific execution targets and effective question selection."""
from __future__ import annotations

from typing import Any

from .common import PipelineError
from .evidence import observed_summary
from .integrity import description_is_current, video_selected
from .paths import resolve_video_path
from .result_rules import target_video_role


def selected_questions(
    case: dict[str, Any], selected_question_ids: set[str]
) -> list[dict[str, Any]]:
    if not case["questions"] and not case.get("quality_curation"):
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
) -> list[dict[str, Any]]:
    role = target_video_role(input_mode)
    candidates = [
        video
        for video in case["videos"]
        if video["role"] == role
    ]
    available = {video["video_id"] for video in candidates}
    missing = selected_video_ids - available
    if missing:
        raise PipelineError(
            f"{role.title()} video IDs not found in {case['case_id']}: "
            f"{', '.join(sorted(missing))}"
        )

    eligible: list[dict[str, Any]] = []
    for video in candidates:
        if selected_video_ids and video["video_id"] not in selected_video_ids:
            continue
        if not video_selected(video, input_mode):
            if video["video_id"] in selected_video_ids:
                raise PipelineError(f"Selected video {case['case_id']}/{video['video_id']} is not ready.")
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
            observed_summary(video)  # Blocks stale annotations after regeneration.
            resolve_video_path(video["local_path"], must_exist=True)
        eligible.append(video)
    return eligible
