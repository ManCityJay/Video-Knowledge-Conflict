"""Shared selection and content provenance for QA, judging and reports."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .core import PipelineError, qa_result_input_mode, video_case_context
from .evidence import description_source_hash, observed_summary, video_sha256

MATH_GROUP = "mathematics_algorithm_conflicts"


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode()).hexdigest()


def question_content(question: dict | None) -> dict | None:
    """Runtime answers must never change the identity of a question/reference."""
    if question is None:
        return None
    return {key: value for key, value in question.items()
            if key not in {"question_only_results", "baseline_results"}}


def video_selected(video: dict, input_mode: str, scope: str | None = None) -> bool:
    parts = Path(video["local_path"]).parts
    # Existing other groups retain their default scope. Math experiments use the
    # curated bucket; legacy control review flags are reported separately.
    scope = scope or ("qualified" if MATH_GROUP in parts else "all")
    if input_mode == "description" and video["role"] != "conflict":
        return False
    if scope == "qualified":
        return ("qualified" in parts and video["status"] == "ready"
                and video.get("human_review") != "rejected"
                and not video.get("qualification_pending")
                and (video["role"] == "control" or video.get("human_review") == "verified"))
    return input_mode == "description" or video["status"] == "ready"


def description_is_current(video: dict) -> bool:
    description = video.get("description")
    if not isinstance(description, dict):
        return False
    if description.get("source_sha256") != description_source_hash(video):
        return False
    if description.get("source") == "video":
        obs = video["video_observation"]
        return description.get("context_en") == obs.get("context_en", obs["summary_en"])
    return True


def qa_fingerprint(case: dict, video: dict, question: dict, input_mode: str,
                   prefix: bool | None = None) -> str:
    context = video_case_context(case, video)
    if input_mode == "video":
        observed_summary(video)
        content = video_sha256(video)
    else:
        if not description_is_current(video):
            raise PipelineError(f"Context is stale for {case['case_id']}/{video['video_id']}. Run description again.")
        content = video["description"]["context_en"]
    return digest({"version": 1, "input": input_mode, "content": content,
                   "question": question["text_en"], "question_id": question["question_id"],
                   "title": context["title"].split(":", 1)[0].strip() if prefix else None})


def current_question(case: dict, video: dict, result: dict) -> dict | None:
    return next((q for q in video_case_context(case, video)["questions"]
                 if q["question_id"] == result.get("question_id")), None)


def qa_is_current(case: dict, video: dict, result: dict) -> bool:
    question = current_question(case, video, result)
    if question is None or result.get("question") != question["text_en"]:
        return False
    mode = qa_result_input_mode(result)
    if mode == "video" and video["status"] != "ready":
        return False
    try:
        if mode == "description" and (not description_is_current(video)
                or result.get("context_text_en") != video["description"]["context_en"]):
            return False
        if result.get("input_fingerprint"):
            return result["input_fingerprint"] == qa_fingerprint(
                case, video, question, mode, result.get("work_title_prefix"))
        # Never certify legacy math results lacking a binding to their inputs.
        return MATH_GROUP not in Path(video["local_path"]).parts
    except (PipelineError, OSError):
        return False


def judgment_fingerprint(case: dict, video: dict, result: dict) -> str:
    context = video_case_context(case, video)
    return digest({"version": 1, "role": video["role"],
                   "question": question_content(current_question(case, video, result)),
                   "conflict_spec": context["conflict_spec"],
                   "final_answer": result.get("final_answer"),
                   "input_fingerprint": result.get("input_fingerprint")})


def judgment_is_current(case: dict, video: dict, result: dict) -> bool:
    judgment = result.get("judgment")
    if not isinstance(judgment, dict) or not qa_is_current(case, video, result):
        return False
    fingerprint = judgment.get("input_fingerprint")
    if fingerprint:
        return fingerprint == judgment_fingerprint(case, video, result)
    return MATH_GROUP not in Path(video["local_path"]).parts


def question_scope_fingerprint(owner: dict, context: dict) -> str:
    return digest({"questions": [question_content(q) for q in owner["questions"]],
                   "case_context": context})


def require_writable_case(case: dict, case_path: Path) -> None:
    """Promoted runtime files are historical inputs, not writable aliases."""
    canonical = case.get("canonical_case_path")
    if canonical:
        raise PipelineError(f"This is a promoted variant snapshot: {case_path}. "
                            f"Operate on its canonical case instead: {canonical}")
