"""Shared QA conditions, effort normalization, record keys and legacy metadata."""
from __future__ import annotations

from typing import Any, Iterable

from .common import PipelineError
from .settings import (
    COSMOS_QA_MODEL,
    FAIRY_TALE_GROUP,
    GEMINI_QA_MODEL,
    GEMMA_QA_MODEL,
    KIMI_QA_MODEL,
    QWEN_QA_MODEL,
    QWEN38_QA_MODEL,
)


def qa_input_mode(input_selection: str) -> str:
    """Control selects a video role while retaining the persisted video medium."""
    return "video" if input_selection == "control" else input_selection


def target_video_role(input_selection: str) -> str:
    if input_selection in ("video", "description"):
        return "conflict"
    if input_selection == "control":
        return "control"
    raise PipelineError(f"Input {input_selection!r} has no video targets.")


def qa_result_input_mode(result: dict[str, Any]) -> str:
    """Treat pre-description results as video results."""
    value = result.get("input_mode", "video")
    return value if isinstance(value, str) else ""


def canonical_verdict(value: str) -> str:
    """Map persisted legacy labels to the current reporting vocabulary."""
    return "context_grounded" if value == "video_grounded" else value


FILTER_RESULT_FIELDS = ("filter_results", "baseline_results")


def filter_field(record: dict[str, Any], name: str) -> Any:
    """Read current metadata first, without rewriting historical records."""
    key = f"filter_{name}"
    return record[key] if key in record else record.get(f"baseline_{name}")


def set_filter_field(record: dict[str, Any], name: str, value: Any) -> None:
    """New records use filter names; resumed records retain their field spelling."""
    key = f"filter_{name}"
    legacy_key = f"baseline_{name}"
    if key not in record and legacy_key in record:
        key = legacy_key
    record[key] = value


QA_THINKING_EFFORTS = {
    GEMINI_QA_MODEL: ("default",),
    QWEN_QA_MODEL: (None, "default"),
    KIMI_QA_MODEL: ("default",),
    COSMOS_QA_MODEL: (None, "default"),
    GEMMA_QA_MODEL: (None, "default"),
    QWEN38_QA_MODEL: (None, "default"),
}
DEFAULT_THINKING_EFFORT = "default"


def normalize_thinking_effort(value: str) -> str | None:
    return None if value == "none" else value


def expand_thinking_efforts(
    values: Iterable[str] | None,
    qa_model: str,
) -> tuple[str | None, ...]:
    try:
        efforts = QA_THINKING_EFFORTS[qa_model]
    except KeyError as exc:
        raise PipelineError(f"Unsupported QA model: {qa_model}") from exc
    requested = list(values or [])
    if not requested:
        return (DEFAULT_THINKING_EFFORT,)
    if "all" in requested:
        return efforts
    selected = {normalize_thinking_effort(value) for value in requested}
    unsupported = selected - set(efforts)
    if unsupported:
        provided = ", ".join(
            "none" if value is None else str(value)
            for value in sorted(unsupported, key=str)
        )
        available = ", ".join(
            "none" if value is None else value
            for value in efforts
        )
        raise PipelineError(
            f"Thinking effort {provided} is not supported by {qa_model}. "
            f"Supported efforts: {available}."
        )
    return tuple(effort for effort in efforts if effort in selected)


def canonical_thinking_effort(model: Any, value: Any) -> Any:
    """Treat legacy Gemini medium results as the new default effort."""
    if model == GEMINI_QA_MODEL and value == "medium":
        return "default"
    return value


def qa_result_thinking_effort(result: dict[str, Any]) -> Any:
    return canonical_thinking_effort(
        result.get("model"), result.get("thinking_effort")
    )


def qa_result_work_title_prefix(result: dict[str, Any]) -> bool | None:
    if qa_result_input_mode(result) != "video":
        return None
    value = result.get("work_title_prefix")
    return value if isinstance(value, bool) else None


def qa_result_based(result: dict[str, Any]) -> bool:
    return result.get("based", False) is True


def qa_result_matches(
    result: dict[str, Any],
    *,
    input_selection: str,
    model: str,
    efforts: set[str | None],
    based: bool = False,
    work_title_prefix: bool | None = None,
) -> bool:
    mode = qa_input_mode(input_selection)
    return (
        result.get("model") == model
        and qa_result_input_mode(result) == mode
        and qa_result_thinking_effort(result) in efforts
        and (mode == "question_only" or qa_result_based(result) is based)
        and (mode != "video" or work_title_prefix is None
             or qa_result_work_title_prefix(result) is work_title_prefix)
    )


def work_title_prefix_condition(
    group: Any,
    input_mode: str,
    enabled: bool,
) -> bool | None:
    """Return the prefix condition for Fairy conflict and control videos."""
    if group == FAIRY_TALE_GROUP and qa_input_mode(input_mode) == "video":
        return bool(enabled)
    return None
