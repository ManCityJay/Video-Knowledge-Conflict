"""Shared exceptions, text utilities and case question contexts."""
from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from typing import Any


ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]*$")


CJK_PATTERN = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")


class PipelineError(Exception):
    """An expected, user-facing pipeline error."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def is_english_text(value: Any) -> bool:
    return (
        isinstance(value, str)
        and bool(value.strip())
        and bool(re.search(r"[A-Za-z]", value))
        and not CJK_PATTERN.search(value)
    )


def normalize_text(value: str) -> str:
    return re.sub(r"\W+", " ", value.lower()).strip()


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def require_nonempty_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise PipelineError(f"{field} must be a non-empty string.")
    return value.strip()


def validate_id(value: Any, field: str) -> str:
    result = require_nonempty_string(value, field)
    if not ID_PATTERN.fullmatch(result):
        raise PipelineError(
            f"{field} must use lowercase letters, numbers, underscores, or hyphens."
        )
    return result


def validate_group(value: Any) -> str:
    return validate_id(value, "group")


def video_case_context(case: dict[str, Any], video: dict[str, Any]) -> dict[str, Any]:
    """Return this video's facts/questions while keeping the parent case identity."""
    context = video.get("variant_context")
    if context is None:
        return case
    return {**case, "title": context.get("title", case["title"]),
            "questions": context["questions"], "conflict_spec": context["conflict_spec"]}


def require_question_only_compatible(
    case: dict[str, Any],
) -> list[dict[str, Any]]:
    """Return shared questions after rejecting private video question scopes."""
    private_videos = [
        video["video_id"]
        for video in case["videos"]
        if video.get("variant_context") is not None
    ]
    if private_videos:
        raise PipelineError(
            f"Case {case['case_id']} has private variant_context questions "
            f"({', '.join(private_videos)}); question_only currently supports "
            "case-level questions only."
        )
    if not case["questions"]:
        raise PipelineError(
            f"Case {case['case_id']} has no questions. Run questions first."
        )
    return case["questions"]
