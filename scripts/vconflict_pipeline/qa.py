"""QA backends and bounded parallel execution."""

from __future__ import annotations

from .integrity import (qa_fingerprint, qa_is_current, require_writable_case)
from .filters import effective_prefix, qa_allowed

import base64
import os
import sys
import threading
import uuid
from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any, Callable, Iterable
from .selection import eligible_videos, selected_questions
from .qa_diagnostics import QADiagnostics, QADiagnosticStage

from .core import (
    PipelineError,
    atomic_write_json,
    grouped_dir,
    iter_case_paths,
    load_case,
    qa_result_input_mode,
    require_question_only_compatible,
    resolve_video_path,
    utc_now,
    video_case_context,
)
from .settings import (
    COSMOS_QA_MODEL,
    DEFAULT_COSMOS_BASE_URL,
    DEFAULT_COSMOS_MAX_TOKENS,
    DEFAULT_GEMMA_BASE_URL,
    DEFAULT_GEMMA_MAX_TOKENS,
    GEMMA_QA_MODEL,
    FAIRY_TALE_GROUP,
    GEMINI_QA_MODEL,
    KIMI_QA_MODEL,
    QWEN_QA_MODEL,
)
from .transport import (
    EmptyResponseTextError,
    OPENROUTER_URL,
    RequestLimiter,
    TransportError,
    extract_response_text,
    get_json,
    make_request_limiter,
    post_json,
    redact,
    require_api_key,
    send_with_retry,
)

REQUEST_TIMEOUT_SECONDS = 600
QWEN_DEFAULT_BASE_HTTP_API_URL = "https://dashscope.aliyuncs.com/api/v1"
KIMI_DEFAULT_BASE_URL = "https://api.moonshot.cn/v1"
QWEN_MAX_LOCAL_VIDEO_BYTES = 100 * 1024 * 1024
KIMI_MAX_REQUEST_BODY_BYTES = 100_000_000
FINAL_ANSWER_PREFIX = "Final answer:"
FINAL_ANSWER_INSTRUCTION = (
    "Conclude with exactly one final line in this format: "
    "Final answer: <your clear, direct answer in one sentence>."
)


class MissingFinalAnswerError(PipelineError):
    """Answer text does not contain a valid final-answer line."""


class TruncatedAnswerError(PipelineError):
    """A local QA response stopped at its output token limit."""


VIDEO_MIME_TYPES = {
    ".mp4": "video/mp4",
    ".m4v": "video/mp4",
    ".mpeg": "video/mpeg",
    ".mpg": "video/mpeg",
    ".mov": "video/mov",
    ".avi": "video/avi",
    ".webm": "video/webm",
}


PayloadBuilder = Callable[[str, str, str | None], dict[str, Any]]
EndpointResolver = Callable[[], str]


@dataclass(frozen=True)
class QABackend:
    model: str
    thinking_efforts: tuple[str | None, ...]
    default_thinking_effort: str | None
    temperature: float
    api_key_variable: str | None
    service: str
    endpoint: EndpointResolver | None
    build_payload: PayloadBuilder | None
    max_body_bytes: int | None = None
    effective_reasoning_effort: str | None = None

    def require_api_key(self) -> str:
        return require_api_key(self.api_key_variable) if self.api_key_variable else ""

    def encode_video(self, video_path: Path) -> str:
        return encode_video_as_data_url(video_path)

    def send_request(
        self,
        payload: dict[str, Any],
        api_key: str,
        timeout: int,
    ) -> dict[str, Any]:
        if self.endpoint is None:
            raise PipelineError(f"{self.service} does not use the JSON HTTP transport.")
        return post_json(
            url=self.endpoint(),
            payload=payload,
            api_key=api_key,
            timeout=timeout,
            service=self.service,
            max_body_bytes=self.max_body_bytes,
        )

    def extract_answer(self, response: dict[str, Any]) -> str:
        return extract_response_text(response, self.service)


def encode_video_as_data_url(video_path: Path) -> str:
    mime = VIDEO_MIME_TYPES.get(video_path.suffix.lower())
    if mime is None:
        supported = ", ".join(sorted(VIDEO_MIME_TYPES))
        raise PipelineError(
            f"Unsupported video format. Supported extensions: {supported}."
        )
    try:
        encoded = base64.b64encode(video_path.read_bytes()).decode("ascii")
    except OSError as exc:
        raise PipelineError(f"Could not read video file: {exc}") from exc
    return f"data:{mime};base64,{encoded}"


def _compatible_endpoint(variable: str, default: str) -> str:
    base_url = os.environ.get(variable, "").strip().rstrip("/") or default
    return f"{base_url}/chat/completions"


def _local_base_url(model: str) -> str:
    config = LOCAL_QA_CONFIGS[model]
    return (
        os.environ.get(config.base_url_variable, "").strip().rstrip("/")
        or config.default_base_url
    )


def _local_video_uri(video_path: Path, service: str) -> str:
    if video_path.suffix.lower() != ".mp4":
        raise PipelineError(f"{service} requires an MP4 video: {video_path}")
    try:
        resolved = video_path.resolve(strict=True)
        if not resolved.is_file():
            raise PipelineError(f"{service} video is not a file: {video_path}")
        return resolved.as_uri()
    except (OSError, ValueError) as exc:
        raise PipelineError(
            f"Could not create a file URI for {service} video {video_path}: {exc}"
        ) from exc


def _dashscope_base_http_api_url() -> str:
    base_url = (
        os.environ.get("DASHSCOPE_BASE_HTTP_API_URL", "").strip()
        or os.environ.get("QWEN_BASE_URL", "").strip()
        or QWEN_DEFAULT_BASE_HTTP_API_URL
    ).rstrip("/")
    compatible_suffix = "/compatible-mode/v1"
    if base_url.endswith(compatible_suffix):
        base_url = f"{base_url[:-len(compatible_suffix)]}/api/v1"
    if not base_url.startswith("https://"):
        raise TransportError("Qwen base URL must use HTTPS.")
    return base_url


def _require_dashscope_sdk() -> ModuleType:
    try:
        import dashscope  # type: ignore[import-not-found]
    except ImportError as exc:
        raise PipelineError(
            'Qwen QA requires DashScope Python SDK 1.24.6 or newer. Install it with: '
            'python -m pip install -U "dashscope>=1.24.6"'
        ) from exc
    version = getattr(dashscope, "__version__", None)
    if isinstance(version, str):
        numeric_version = tuple(
            int(part) for part in version.split(".")[:3] if part.isdigit()
        )
        if numeric_version and numeric_version < (1, 24, 6):
            raise PipelineError(
                f"Qwen QA requires DashScope Python SDK 1.24.6 or newer "
                f"(installed: {version}). Upgrade it with: "
                'python -m pip install -U "dashscope>=1.24.6"'
            )
    return dashscope


def _qwen_video_uri(video_path: Path) -> str:
    if video_path.suffix.lower() not in VIDEO_MIME_TYPES:
        supported = ", ".join(sorted(VIDEO_MIME_TYPES))
        raise PipelineError(
            f"Unsupported video format. Supported extensions: {supported}."
        )
    try:
        size = video_path.stat().st_size
    except OSError as exc:
        raise PipelineError(f"Could not stat video file: {exc}") from exc
    if size > QWEN_MAX_LOCAL_VIDEO_BYTES:
        raise PipelineError(
            f"Video is too large for Qwen local-file input ({size} bytes; maximum "
            f"{QWEN_MAX_LOCAL_VIDEO_BYTES} bytes). Use a public URL or OSS for videos "
            "larger than 100 MiB."
        )
    try:
        return video_path.resolve().as_uri()
    except (OSError, ValueError) as exc:
        raise PipelineError(f"Could not create a file URI for {video_path}: {exc}") from exc


def _response_field(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, Mapping):
        return value.get(name, default)
    return getattr(value, name, default)


def _plain_json_value(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, Mapping):
        return {str(key): _plain_json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain_json_value(item) for item in value]
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        return _plain_json_value(to_dict())
    try:
        return _plain_json_value(dict(value))
    except (TypeError, ValueError):
        return str(value)


def _normalize_dashscope_response(response: Any) -> dict[str, Any]:
    status_code = _response_field(response, "status_code")
    if status_code is not None:
        try:
            status_number = int(status_code)
        except (TypeError, ValueError):
            status_number = None
        if status_number is not None and status_number != 200:
            code = _response_field(response, "code")
            message = _response_field(response, "message", "Request failed")
            detail = f"{code}: {message}" if code else str(message)
            raise TransportError(
                f"Qwen request failed (HTTP {status_number}): {detail}"
            )

    output = _response_field(response, "output")
    choices = _response_field(output, "choices")
    if not isinstance(choices, (list, tuple)) or not choices:
        raise TransportError("Qwen response did not contain an answer choice.")
    message = _response_field(choices[0], "message")
    if not isinstance(message, Mapping) and not any(
        hasattr(message, field) for field in ("content", "role", "reasoning_content")
    ):
        raise TransportError("Qwen response did not contain a message.")
    content = _response_field(message, "content")
    if isinstance(content, str):
        answer = content
    elif isinstance(content, (list, tuple)):
        answer = "".join(
            text
            for part in content
            if isinstance((text := _response_field(part, "text")), str)
        )
        if not answer.strip() and any(
            (not isinstance(part, Mapping) and not hasattr(part, "text"))
            or (_response_field(part, "text") is not None
                and not isinstance(_response_field(part, "text"), str))
            for part in content
        ):
            raise TransportError("Qwen response did not contain textual content.")
    else:
        if content is not None:
            raise TransportError("Qwen response did not contain textual content.")
        answer = ""
    if not answer.strip():
        raise EmptyResponseTextError("Qwen response did not contain textual content.")

    normalized: dict[str, Any] = {
        "choices": [{"message": {"content": answer}}],
    }
    request_id = _response_field(response, "request_id") or _response_field(
        response, "id"
    )
    if request_id is not None:
        normalized["id"] = str(request_id)
    usage = _response_field(response, "usage")
    if usage is None:
        usage = _response_field(output, "usage")
    plain_usage = _plain_json_value(usage)
    if isinstance(plain_usage, dict):
        normalized["usage"] = plain_usage
    return normalized


def _send_qwen_request(
    *,
    prompt_text: str,
    video_uri: str | None,
    thinking_effort: str | None,
    api_key: str,
    timeout: int,
) -> dict[str, Any]:
    if thinking_effort not in (None, "default"):
        raise PipelineError("Qwen thinking effort must be none or default.")
    dashscope = _require_dashscope_sdk()
    dashscope.base_http_api_url = _dashscope_base_http_api_url()
    content: list[dict[str, Any]] = []
    if video_uri is not None:
        content.append({"video": video_uri, "fps": 2})
    content.append({"text": prompt_text})
    messages = [{"role": "user", "content": content}]
    try:
        response = dashscope.MultiModalConversation.call(
            api_key=api_key,
            model=QWEN_QA_MODEL,
            messages=messages,
            temperature=0.0,
            enable_thinking=thinking_effort is not None,
            request_timeout=timeout,
        )
    except Exception as exc:
        raise TransportError(
            f"Qwen request failed: {redact(str(exc), api_key)}"
        ) from exc
    return _normalize_dashscope_response(response)


def _gemini_payload(
    prompt_text: str,
    video_data_url: str,
    thinking_effort: str | None,
) -> dict[str, Any]:
    if thinking_effort != "default":
        raise PipelineError("Gemini thinking effort must be default.")
    return {
        "model": GEMINI_QA_MODEL,
        "temperature": 0.0,
        "reasoning": {"effort": "medium"},
        "stream": False,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "video_url", "video_url": {"url": video_data_url}},
                    {"type": "text", "text": prompt_text},
                ],
            }
        ],
    }


def _kimi_payload(
    prompt_text: str,
    video_data_url: str,
    thinking_effort: str | None,
) -> dict[str, Any]:
    if thinking_effort != "default":
        raise PipelineError(
            "Kimi K3 cannot disable thinking; use default (effective max)."
        )
    # The service fixes temperature=1 and defaults reasoning_effort to max.
    # Those fields and completion-token caps are intentionally not sent.
    return {
        "model": KIMI_QA_MODEL,
        "stream": False,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "video_url", "video_url": {"url": video_data_url}},
                    {"type": "text", "text": prompt_text},
                ],
            }
        ],
    }


def _question_prompt(question: str) -> str:
    return f"{question}\n\n{FINAL_ANSWER_INSTRUCTION}"


def _video_question_prompt(
    question: str,
    *,
    work_title: str | None,
    work_title_prefix: bool,
    based: bool = False,
) -> str:
    if work_title_prefix:
        if not work_title:
            raise PipelineError("A work title is required when its prefix is enabled.")
        question = f"This is a video clip from the work {work_title}. {question}"
    if based:
        question = f"Answer the question based on the video.\n\n{question}"
    return _question_prompt(question)


def _description_prompt(context: str, question: str, *, based: bool = False) -> str:
    instruction = "\n\nAnswer the question based on the context above." if based else ""
    return f"{context}{instruction}\n\nQuestion:\n{_question_prompt(question)}"


def extract_final_answer(raw_answer: str) -> str:
    """Accept the final-answer marker anywhere on the last non-empty line."""
    lines = raw_answer.splitlines()
    while lines and not lines[-1].strip():
        lines.pop()
    final_line = lines[-1].strip() if lines else ""
    _, marker, final_answer = final_line.rpartition(FINAL_ANSWER_PREFIX)
    final_answer = final_answer.strip()
    if not marker or not final_answer:
        raise MissingFinalAnswerError(
            f"QA response's last non-empty line must contain "
            f"'{FINAL_ANSWER_PREFIX}' followed by a non-empty answer."
        )
    return final_answer


def _gemini_description_payload(
    prompt_text: str,
    thinking_effort: str | None,
) -> dict[str, Any]:
    if thinking_effort != "default":
        raise PipelineError("Gemini thinking effort must be default.")
    return {
        "model": GEMINI_QA_MODEL,
        "temperature": 0.0,
        "reasoning": {"effort": "medium"},
        "stream": False,
        "messages": [{"role": "user", "content": prompt_text}],
    }


def _kimi_description_payload(
    prompt_text: str,
    thinking_effort: str | None,
) -> dict[str, Any]:
    if thinking_effort != "default":
        raise PipelineError(
            "Kimi K3 cannot disable thinking; use default (effective max)."
        )
    return {
        "model": KIMI_QA_MODEL,
        "stream": False,
        "messages": [{"role": "user", "content": prompt_text}],
    }


def _cosmos_prompt(prompt_text: str, thinking_effort: str | None) -> str:
    if not prompt_text.endswith(FINAL_ANSWER_INSTRUCTION):
        raise PipelineError("Cosmos3-Nano question is missing its final-answer instruction.")
    task = prompt_text[: -len(FINAL_ANSWER_INSTRUCTION)].rstrip()
    if thinking_effort is None:
        instruction = "Answer without using <think> tags."
    elif thinking_effort == "default":
        instruction = (
            "Answer the question using the following format:\n"
            "<think>\nYour reasoning.\n</think>\n"
            "Write your final answer immediately after the </think> tag."
        )
    else:
        raise PipelineError("Cosmos3-Nano thinking effort must be none or default.")
    return f"{task}\n\n{instruction}\n\n{FINAL_ANSWER_INSTRUCTION}"


def _cosmos_payload(
    *,
    prompt_text: str,
    video_uri: str | None,
    thinking_effort: str | None,
    served_model_id: str,
    max_tokens: int,
) -> dict[str, Any]:
    content: str | list[dict[str, Any]] = _cosmos_prompt(
        prompt_text, thinking_effort
    )
    if video_uri is not None:
        content = [
            {"type": "video_url", "video_url": {"url": video_uri}},
            {"type": "text", "text": content},
        ]
    payload: dict[str, Any] = {
        "model": served_model_id,
        "temperature": 0.0,
        "seed": 0,
        "max_tokens": max_tokens,
        "stream": False,
        "messages": [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": content},
        ],
    }
    if video_uri is not None:
        # The Qwen3VL loader samples by fps even with num_frames=-1. Use the
        # generic loader to pass every decoded frame to the HF video processor,
        # which then performs the single 4 fps sampling pass.
        payload["media_io_kwargs"] = {
            "video": {"video_backend": "opencv", "num_frames": -1, "fps": -1}
        }
        payload["mm_processor_kwargs"] = {"fps": 4, "do_sample_frames": True}
    return payload


def _gemma_payload(
    *,
    prompt_text: str,
    video_uri: str | None,
    thinking_effort: str | None,
    served_model_id: str,
    max_tokens: int,
) -> dict[str, Any]:
    if thinking_effort not in (None, "default"):
        raise PipelineError("Gemma 4 thinking effort must be none or default.")
    content: str | list[dict[str, Any]] = prompt_text
    if video_uri is not None:
        content = [
            {"type": "video_url", "video_url": {"url": video_uri}},
            {"type": "text", "text": prompt_text},
        ]
    payload: dict[str, Any] = {
        "model": served_model_id,
        "temperature": 0.0,
        "seed": 0,
        "max_tokens": max_tokens,
        "stream": False,
        "chat_template_kwargs": {"enable_thinking": thinking_effort == "default"},
        "messages": [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": content},
        ],
    }
    if video_uri is not None:
        # Sample the whole video once. Gemma's vLLM processor uses 70 tokens
        # per frame; no Cosmos fps resampling or image-budget override applies.
        payload["media_io_kwargs"] = {
            "video": {"video_backend": "opencv", "num_frames": 32, "fps": -1}
        }
    return payload


@dataclass(frozen=True)
class LocalQAConfig:
    base_url_variable: str
    default_base_url: str
    workers_argument: str
    max_tokens_argument: str
    default_max_tokens: int
    build_payload: Callable[..., dict[str, Any]]


LOCAL_QA_CONFIGS = {
    COSMOS_QA_MODEL: LocalQAConfig(
        "COSMOS_BASE_URL", DEFAULT_COSMOS_BASE_URL, "cosmos_workers",
        "cosmos_max_tokens", DEFAULT_COSMOS_MAX_TOKENS, _cosmos_payload,
    ),
    GEMMA_QA_MODEL: LocalQAConfig(
        "GEMMA_BASE_URL", DEFAULT_GEMMA_BASE_URL, "gemma_workers",
        "gemma_max_tokens", DEFAULT_GEMMA_MAX_TOKENS, _gemma_payload,
    ),
}


def make_qa_request_limiter(args: Any) -> RequestLimiter:
    config = LOCAL_QA_CONFIGS.get(args.qa_model)
    if config is not None:
        return RequestLimiter(getattr(args, config.workers_argument))
    return make_request_limiter(args)


def local_qa_max_tokens(args: Any) -> int | None:
    config = LOCAL_QA_CONFIGS.get(args.qa_model)
    return getattr(args, config.max_tokens_argument) if config is not None else None


GEMINI_BACKEND = QABackend(
    model=GEMINI_QA_MODEL,
    thinking_efforts=("default",),
    default_thinking_effort="default",
    temperature=0.0,
    api_key_variable="OPENROUTER_API_KEY",
    service="OpenRouter",
    endpoint=lambda: OPENROUTER_URL,
    build_payload=_gemini_payload,
    effective_reasoning_effort="medium",
)
QWEN_BACKEND = QABackend(
    model=QWEN_QA_MODEL,
    thinking_efforts=(None, "default"),
    default_thinking_effort="default",
    temperature=0.0,
    api_key_variable="DASHSCOPE_API_KEY",
    service="Qwen",
    endpoint=None,
    build_payload=None,
)
KIMI_BACKEND = QABackend(
    model=KIMI_QA_MODEL,
    thinking_efforts=("default",),
    default_thinking_effort="default",
    temperature=1.0,
    api_key_variable="MOONSHOT_API_KEY",
    service="Kimi",
    endpoint=lambda: _compatible_endpoint("MOONSHOT_BASE_URL", KIMI_DEFAULT_BASE_URL),
    build_payload=_kimi_payload,
    max_body_bytes=KIMI_MAX_REQUEST_BODY_BYTES,
    effective_reasoning_effort="max",
)
COSMOS_BACKEND = QABackend(
    model=COSMOS_QA_MODEL,
    thinking_efforts=(None, "default"),
    default_thinking_effort="default",
    temperature=0.0,
    api_key_variable=None,
    service="Cosmos3-Nano",
    endpoint=lambda: f"{_local_base_url(COSMOS_QA_MODEL)}/chat/completions",
    build_payload=None,
)
GEMMA_BACKEND = QABackend(
    model=GEMMA_QA_MODEL,
    thinking_efforts=(None, "default"),
    default_thinking_effort="default",
    temperature=0.0,
    api_key_variable=None,
    service="Gemma 4",
    endpoint=lambda: f"{_local_base_url(GEMMA_QA_MODEL)}/chat/completions",
    build_payload=None,
)
QA_BACKENDS = {
    backend.model: backend
    for backend in (GEMINI_BACKEND, QWEN_BACKEND, KIMI_BACKEND, COSMOS_BACKEND, GEMMA_BACKEND)
}


def get_backend(model: str) -> QABackend:
    try:
        return QA_BACKENDS[model]
    except KeyError as exc:
        raise PipelineError(f"Unsupported QA model: {model}") from exc


def normalize_thinking_effort(value: str) -> str | None:
    return None if value == "none" else value


def expand_thinking_efforts(
    values: Iterable[str] | None,
    qa_model: str,
) -> tuple[str | None, ...]:
    backend = get_backend(qa_model)
    requested = list(values or [])
    if not requested:
        return (backend.default_thinking_effort,)
    if "all" in requested:
        return backend.thinking_efforts
    selected = {normalize_thinking_effort(value) for value in requested}
    unsupported = selected - set(backend.thinking_efforts)
    if unsupported:
        provided = ", ".join(
            "none" if value is None else str(value)
            for value in sorted(unsupported, key=str)
        )
        available = ", ".join(
            "none" if value is None else value
            for value in backend.thinking_efforts
        )
        raise PipelineError(
            f"Thinking effort {provided} is not supported by {qa_model}. "
            f"Supported efforts: {available}."
        )
    return tuple(effort for effort in backend.thinking_efforts if effort in selected)


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


def work_title_prefix_condition(
    group: Any,
    input_mode: str,
    enabled: bool,
) -> bool | None:
    """Return the prefix condition only for the Fairy video experiment."""
    if group == FAIRY_TALE_GROUP and input_mode == "video":
        return bool(enabled)
    return None


def qa_run_key(
    input_mode: str,
    question_id: Any,
    model: Any,
    thinking_effort: Any,
    *,
    based: bool = False,
    work_title_prefix: bool | None = None,
) -> tuple[Any, ...]:
    key = (input_mode, question_id, model, thinking_effort)
    if input_mode != "question_only":
        key = (*key, based)
    return (*key, work_title_prefix) if work_title_prefix is not None else key


def qa_result_key(
    result: dict[str, Any],
    *,
    include_work_title_prefix: bool = False,
) -> tuple[Any, ...]:
    input_mode = qa_result_input_mode(result)
    key = (
        input_mode,
        result.get("question_id"),
        result.get("model"),
        qa_result_thinking_effort(result),
    )
    if input_mode != "question_only":
        key = (*key, qa_result_based(result))
    if input_mode == "video" and include_work_title_prefix:
        return (*key, qa_result_work_title_prefix(result))
    return key


def run_qa_batch(
    *,
    input_mode: str,
    video_path: Path | None,
    context_text: str | None,
    work_title: str | None,
    work_title_prefix: bool | None,
    question_runs: list[tuple[dict[str, Any], str | None]],
    qa_model: str,
    api_key: str,
    timeout: int,
    max_retries: int,
    request_limiter: RequestLimiter,
    local_served_model_id: str | None = None,
    local_max_tokens: int | None = None,
    based: bool = False,
    diagnostics: QADiagnostics | None = None,
    diagnostic_stage: QADiagnosticStage = "main",
) -> tuple[list[dict[str, Any]], list[tuple[str, str | None, str]]]:
    backend = get_backend(qa_model)
    if input_mode == "video":
        if video_path is None:
            raise PipelineError("Video input requires a local video path.")
        if work_title_prefix is True and not work_title:
            raise PipelineError(
                "Video input requires a work title when its prefix is enabled."
            )
        if qa_model == QWEN_QA_MODEL:
            video_input = _qwen_video_uri(video_path)
        elif qa_model in LOCAL_QA_CONFIGS:
            video_input = _local_video_uri(video_path, backend.service)
        else:
            video_input = backend.encode_video(video_path)
    elif input_mode == "description":
        if context_text is None:
            raise PipelineError("Description input requires context text.")
        video_input = None
    elif input_mode == "question_only":
        if based:
            raise PipelineError("Question-only input does not support --based.")
        if work_title_prefix is not None:
            raise PipelineError(
                "Question-only input does not support a work-title prefix."
            )
        video_input = None
    else:
        raise PipelineError(f"Unsupported QA input mode: {input_mode}")
    results: list[dict[str, Any]] = []
    failures: list[tuple[str, str | None, str]] = []
    for question, thinking_effort in question_runs:
        if input_mode == "video":
            prompt_text = _video_question_prompt(
                question["text_en"],
                work_title=work_title,
                work_title_prefix=work_title_prefix is True,
                based=based,
            )
        elif input_mode == "description":
            prompt_text = _description_prompt(context_text, question["text_en"], based=based)
        else:
            prompt_text = _question_prompt(question["text_en"])
        try:
            if qa_model == QWEN_QA_MODEL:
                response = send_with_retry(
                    lambda thinking_effort=thinking_effort: _send_qwen_request(
                        prompt_text=prompt_text,
                        video_uri=video_input,
                        thinking_effort=thinking_effort,
                        api_key=api_key,
                        timeout=timeout,
                    ),
                    request_limiter=request_limiter,
                    max_retries=max_retries,
                )
            else:
                if qa_model in LOCAL_QA_CONFIGS:
                    if local_served_model_id is None:
                        raise PipelineError(f"{backend.service} served model ID is missing.")
                    config = LOCAL_QA_CONFIGS[qa_model]
                    payload = config.build_payload(
                        prompt_text=prompt_text,
                        video_uri=video_input,
                        thinking_effort=thinking_effort,
                        served_model_id=local_served_model_id,
                        max_tokens=(local_max_tokens if local_max_tokens is not None
                                    else config.default_max_tokens),
                    )
                elif input_mode != "video" and qa_model == GEMINI_QA_MODEL:
                    payload = _gemini_description_payload(prompt_text, thinking_effort)
                elif input_mode != "video" and qa_model == KIMI_QA_MODEL:
                    payload = _kimi_description_payload(prompt_text, thinking_effort)
                elif backend.build_payload is None or video_input is None:
                    raise PipelineError(
                        f"{backend.service} does not use a Base64 payload builder."
                    )
                else:
                    payload = backend.build_payload(
                        prompt_text, video_input, thinking_effort
                    )
                response = send_with_retry(
                    lambda payload=payload: backend.send_request(
                        payload, api_key, timeout
                    ),
                    request_limiter=request_limiter,
                    max_retries=max_retries,
                )
            if qa_model in LOCAL_QA_CONFIGS:
                choices = response.get("choices")
                if (
                    isinstance(choices, list)
                    and choices
                    and isinstance(choices[0], dict)
                    and choices[0].get("finish_reason") == "length"
                ):
                    raise TruncatedAnswerError(
                        f"{backend.service} answer was truncated at max_tokens; "
                        f"increase --{LOCAL_QA_CONFIGS[qa_model].max_tokens_argument.replace('_', '-')} "
                        "and rerun this QA."
                    )
            raw_answer = backend.extract_answer(response)
            final_answer = extract_final_answer(raw_answer)
        except PipelineError as exc:
            if diagnostics is not None:
                if isinstance(exc, TruncatedAnswerError):
                    diagnostics.record(diagnostic_stage, "max_tokens_truncated")
                elif isinstance(exc, (MissingFinalAnswerError, EmptyResponseTextError)):
                    diagnostics.record(diagnostic_stage, "missing_final_answer")
            failures.append(
                (question["question_id"], thinking_effort, str(exc))
            )
            continue
        result: dict[str, Any] = {
            "run_id": uuid.uuid4().hex,
            "timestamp": utc_now(),
            "input_mode": input_mode,
            "question_id": question["question_id"],
            "question": question["text_en"],
            "raw_answer": raw_answer,
            "final_answer": final_answer,
            "model": qa_model,
            "thinking_effort": thinking_effort,
            "temperature": backend.temperature,
            "request_id": response.get("id"),
            "judgment": None,
        }
        if input_mode == "description":
            result["context_text_en"] = context_text
        elif work_title_prefix is not None:
            result["work_title_prefix"] = work_title_prefix
        if input_mode != "question_only":
            result["based"] = based
        if backend.effective_reasoning_effort is not None:
            result["effective_reasoning_effort"] = backend.effective_reasoning_effort
        if qa_model == GEMMA_QA_MODEL:
            message = response["choices"][0]["message"]
            for field in ("reasoning", "reasoning_content"):
                reasoning = message.get(field)
                if isinstance(reasoning, str) and reasoning.strip():
                    result["reasoning_content"] = reasoning
                    break
        if isinstance(response.get("usage"), dict):
            result["usage"] = response["usage"]
        results.append(result)
    return results, failures


def _preflight_local_videos(
    args: Any, loaded: list[tuple[Path, dict[str, Any]]]
) -> None:
    if args.input != "video":
        return
    selected_videos = set(args.video_id or [])
    for _, case in loaded:
        for video in eligible_videos(
            case, input_mode=args.input, selected_video_ids=selected_videos,
            video_scope=getattr(args, "video_scope", None),
            based=bool(getattr(args, "based", False)),
        ):
            path = resolve_video_path(video["local_path"], must_exist=True)
            _local_video_uri(path, get_backend(args.qa_model).service)


def _local_served_model_id(model: str, timeout: int) -> str:
    service = get_backend(model).service
    response = get_json(
        url=f"{_local_base_url(model)}/models",
        timeout=min(timeout, 10),
        service=service,
    )
    models = response.get("data")
    if not isinstance(models, list) or not models:
        raise PipelineError(f"{service} /models returned no served models.")
    ids = [
        item.get("id")
        for item in models
        if isinstance(item, dict)
        and isinstance(item.get("id"), str)
        and item["id"].strip()
    ]
    if len(ids) != len(models):
        raise PipelineError(f"{service} /models returned an invalid model ID.")
    if model in ids:
        return model
    if len(ids) == 1:
        return ids[0]
    raise PipelineError(
        f"{service} /models returned multiple models without a unique "
        f"{model} entry: {', '.join(ids)}."
    )


def preflight_qa_backend(
    args: Any, loaded: list[tuple[Path, dict[str, Any]]] | None = None
) -> str | None:
    backend = get_backend(args.qa_model)
    expand_thinking_efforts(args.thinking_effort, args.qa_model)
    if args.qa_model == QWEN_QA_MODEL:
        _require_dashscope_sdk()
    backend.require_api_key()
    if args.qa_model in LOCAL_QA_CONFIGS:
        if loaded is not None:
            _preflight_local_videos(args, loaded)
        return _local_served_model_id(args.qa_model, args.timeout)
    return None


def command_qa(
    args: Any, *, local_served_model_id: str | None = None,
    diagnostics: QADiagnostics | None = None,
) -> int:
    backend = get_backend(args.qa_model)
    if args.qa_model == QWEN_QA_MODEL:
        _require_dashscope_sdk()
    api_key = backend.require_api_key()
    request_limiter = make_qa_request_limiter(args)
    if args.qa_model in LOCAL_QA_CONFIGS and local_served_model_id is None:
        local_served_model_id = _local_served_model_id(args.qa_model, args.timeout)
    selected_videos = set(args.video_id or [])
    selected_question_ids = set(args.question_id or [])
    efforts = expand_thinking_efforts(args.thinking_effort, args.qa_model)
    prefix_condition = work_title_prefix_condition(
        args.group,
        args.input,
        args.with_work_title_prefix,
    )
    based_condition = bool(getattr(args, "based", False))
    dataset_dir = grouped_dir(args.dataset_dir, args.group)
    case_paths = iter_case_paths(dataset_dir, args.case_id)
    completed = 0
    failures = 0

    def run_case(case_path: Path) -> tuple[int, int]:
        case = load_case(case_path)
        require_writable_case(case, case_path)
        if args.input == "question_only":
            selected = selected_questions(
                {**case, "questions": require_question_only_compatible(case)},
                selected_question_ids,
            )
            jobs: list[tuple[dict[str, Any], list[tuple[dict[str, Any], str | None]]]] = []
            for question in selected:
                existing = {
                    qa_result_key(result)
                    for result in question.get("question_only_results", [])
                }
                pending = [
                    (question, effort)
                    for effort in efforts
                    if qa_run_key(
                        "question_only",
                        question["question_id"],
                        args.qa_model,
                        effort,
                    )
                    not in existing
                ]
                if pending:
                    jobs.append((question, pending))

            if not jobs:
                return 0, 0

            def run_question(
                pending: list[tuple[dict[str, Any], str | None]],
            ) -> tuple[list[dict[str, Any]], list[tuple[str, str | None, str]]]:
                return run_qa_batch(
                    input_mode="question_only",
                    video_path=None,
                    context_text=None,
                    work_title=None,
                    work_title_prefix=None,
                    question_runs=pending,
                    qa_model=args.qa_model,
                    api_key=api_key,
                    timeout=args.timeout,
                    max_retries=args.max_retries,
                    request_limiter=request_limiter,
                    local_served_model_id=local_served_model_id,
                    local_max_tokens=local_qa_max_tokens(args),
                    diagnostics=diagnostics,
                )

            case_completed = 0
            case_failures = 0
            write_lock = threading.Lock()
            with ThreadPoolExecutor(
                max_workers=min(args.qa_workers, len(jobs))
            ) as executor:
                futures = {
                    executor.submit(run_question, pending): question
                    for question, pending in jobs
                }
                for future in as_completed(futures):
                    question = futures[future]
                    try:
                        results, run_failures = future.result()
                    except PipelineError as exc:
                        case_failures += 1
                        print(
                            f"Error in QA {case['case_id']}/"
                            f"{question['question_id']}: {exc}",
                            file=sys.stderr,
                        )
                        continue
                    for question_id, effort, error in run_failures:
                        effort_name = "none" if effort is None else effort
                        print(
                            f"Error in QA {case['case_id']}/{question_id}/"
                            f"{effort_name}: {error}",
                            file=sys.stderr,
                        )
                    case_failures += len(run_failures)
                    if results:
                        with write_lock:
                            question.setdefault("question_only_results", []).extend(
                                results
                            )
                            atomic_write_json(case_path, case)
                    case_completed += len(results)
                    print(
                        f"QA question_only {case['case_id']}/"
                        f"{question['question_id']}: wrote {len(results)} result(s)"
                    )
            return case_completed, case_failures

        jobs: list[dict[str, Any]] = []
        for video in eligible_videos(
            case, input_mode=args.input, selected_video_ids=selected_videos,
            video_scope=getattr(args, "video_scope", None), based=based_condition,
        ):
            path = (resolve_video_path(video["local_path"], must_exist=True)
                    if args.input == "video" else None)
            context_text = video["description"]["context_en"] if args.input == "description" else None
            context = video_case_context(case, video)
            questions = selected_questions(context, selected_question_ids)

            existing = {
                qa_result_key(
                    result,
                    include_work_title_prefix=prefix_condition is not None,
                )
                for result in video["qa_results"]
                if qa_is_current(case, video, result)
            }
            pending = [
                (question, effort)
                for effort in efforts
                for question in questions
                if qa_allowed(case, video, question, args.qa_model, effort,
                              effective_prefix(args.group, args.with_work_title_prefix), args.input)
                if qa_run_key(
                    args.input,
                    question["question_id"],
                    args.qa_model,
                    effort,
                    based=based_condition,
                    work_title_prefix=prefix_condition,
                )
                not in existing
            ]
            if pending:
                jobs.append(
                    {
                        "video": video,
                        "path": path,
                        "context_text": context_text,
                        "pending": pending,
                    }
                )

        if not jobs:
            return 0, 0

        def run(
            job: dict[str, Any],
        ) -> tuple[list[dict[str, Any]], list[tuple[str, str | None, str]]]:
            context = video_case_context(case, job["video"])
            fingerprints = {q["question_id"]: qa_fingerprint(
                case, job["video"], q, args.input, prefix_condition,
                based=based_condition) for q, _ in job["pending"]}
            results, failures = run_qa_batch(
                input_mode=args.input,
                video_path=job["path"],
                context_text=job["context_text"],
                work_title=(
                    context["title"].split(":", 1)[0].strip()
                    if prefix_condition is True
                    else None
                ),
                work_title_prefix=prefix_condition,
                question_runs=job["pending"],
                qa_model=args.qa_model,
                api_key=api_key,
                timeout=args.timeout,
                max_retries=args.max_retries,
                request_limiter=request_limiter,
                local_served_model_id=local_served_model_id,
                local_max_tokens=local_qa_max_tokens(args),
                based=based_condition,
                diagnostics=diagnostics,
                diagnostic_stage=(
                    "control filter" if job["video"]["role"] == "control" else "main"
                ),
            )
            # Bind to inputs from before the provider request. If files change
            # during the request, the returned result will immediately be stale.
            for result in results:
                result["input_fingerprint"] = fingerprints[result["question_id"]]
            return results, failures

        case_completed = 0
        case_failures = 0
        write_lock = threading.Lock()
        with ThreadPoolExecutor(max_workers=min(args.qa_workers, len(jobs))) as executor:
            futures = {executor.submit(run, job): job["video"] for job in jobs}
            for future in as_completed(futures):
                video = futures[future]
                try:
                    results, run_failures = future.result()
                except PipelineError as exc:
                    case_failures += 1
                    print(
                        f"Error in QA {case['case_id']}/{video['video_id']}: {exc}",
                        file=sys.stderr,
                    )
                    continue
                for question_id, effort, error in run_failures:
                    effort_name = "none" if effort is None else effort
                    print(
                        f"Error in QA {case['case_id']}/{video['video_id']}/"
                        f"{question_id}/{effort_name}: {error}",
                        file=sys.stderr,
                    )
                case_failures += len(run_failures)
                if results:
                    with write_lock:
                        video["qa_results"].extend(results)
                        atomic_write_json(case_path, case)
                case_completed += len(results)
                print(
                    f"QA {args.input} {case['case_id']}/{video['video_id']}: "
                    f"wrote {len(results)} result(s)"
                )
        return case_completed, case_failures

    with ThreadPoolExecutor(max_workers=min(args.case_workers, len(case_paths))) as executor:
        futures = {executor.submit(run_case, path): path for path in case_paths}
        for future in as_completed(futures):
            path = futures[future]
            try:
                done, failed = future.result()
            except PipelineError as exc:
                failures += 1
                print(f"Error in QA case {path.stem}: {exc}", file=sys.stderr)
                continue
            completed += done
            failures += failed
    print(f"Wrote {completed} QA result(s) into case JSON files.")
    return 1 if failures else 0
