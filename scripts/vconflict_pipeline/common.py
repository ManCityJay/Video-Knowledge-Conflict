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
    result = case if context is None else {
        **case, "title": context.get("title", case["title"]),
        "questions": context["questions"], "conflict_spec": context["conflict_spec"]}
    # Curation removes individual video/question associations without deleting
    # a shared question that is still valid for another video.
    if "question_ids" in video:
        retained = set(video["question_ids"])
        result = {**result, "questions": [
            q for q in result["questions"] if q["question_id"] in retained]}
    return result


def require_question_only_compatible(
    case: dict[str, Any],
) -> list[dict[str, Any]]:
    """Return effective conflict questions for the standalone experiment."""
    questions = [question for _, question in conflict_question_scopes(case)]
    if not questions and not case.get('quality_curation'):
        raise PipelineError(f"Case {case['case_id']} has no conflict questions. Run questions first.")
    return questions


def conflict_question_scopes(case):
    """Cover every conflict's effective questions, reusing identical shared scopes.

    Private variant questions remain isolated even when question IDs match.
    Question-only execution does not require ready media or descriptions.
    """
    seen = set()
    for video in case['videos']:
        if video['role'] != 'conflict':
            continue
        scope = video['video_id'] if video.get('variant_context') is not None else 'case'
        for question in video_case_context(case, video)['questions']:
            key = (scope, question['question_id'])
            if key not in seen:
                seen.add(key)
                yield video, question


def question_only_records(question):
    """Read standalone and filter storage without copying or migrating records."""
    from .result_rules import FILTER_RESULT_FIELDS, filter_field
    records = []
    for field in FILTER_RESULT_FIELDS:
        records.extend(result for result in question.get(field, [])
                       if filter_field(result, 'stage') == 'question_only')
    records.extend(question.get('question_only_results', []))
    return records
