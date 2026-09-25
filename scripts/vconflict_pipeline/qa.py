"""QA backends and bounded parallel execution."""

from __future__ import annotations

from .integrity import (video_selected, description_is_current, qa_fingerprint, qa_is_current, require_writable_case)

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
from .evidence import observed_summary

from .core import (
    PipelineError,
    atomic_write_json,
    grouped_dir,
    iter_case_paths,
    load_case,
    qa_result_input_mode,
    require_question_only_compatible,
    resolve_video_path,
    sha256_text,
    utc_now,
    video_case_context,
)
from .settings import (
    COSMOS_QA_MODEL,
    DEFAULT_COSMOS_BASE_URL,
    DEFAULT_COSMOS_MAX_TOKENS,
    FAIRY_TALE_GROUP,
    GEMINI_QA_MODEL,
    KIMI_QA_MODEL,
    QWEN_QA_MODEL,
)
from .transport import (
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


def _cosmos_base_url() -> str:
    return (
        os.environ.get("COSMOS_BASE_URL", "").strip().rstrip("/")
        or DEFAULT_COSMOS_BASE_URL
    )


def _cosmos_video_uri(video_path: Path) -> str:
    if video_path.suffix.lower() != ".mp4":
        raise PipelineError(f"Cosmos3-Nano requires an MP4 video: {video_path}")
    try:
        resolved = video_path.resolve(strict=True)
        if not resolved.is_file():
            raise PipelineError(f"Cosmos3-Nano video is not a file: {video_path}")
        return resolved.as_uri()
    except (OSError, ValueError) as exc:
        raise PipelineError(
            f"Could not create a file URI for Cosmos3-Nano video {video_path}: {exc}"
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
    content = _response_field(message, "content")
    if isinstance(content, str):
        answer = content
    elif isinstance(content, (list, tuple)):
        answer = "".join(
            text
            for part in content
            if isinstance((text := _response_field(part, "text")), str)
        )
    else:
        answer = ""
    if not answer.strip():
        raise TransportError("Qwen response did not contain textual content.")

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
) -> str:
    if not work_title_prefix:
        return _question_prompt(question)
    if not work_title:
        raise PipelineError("A work title is required when its prefix is enabled.")
    return _question_prompt(
        f"This is a video clip from the work {work_title}. {question}"
    )


def _description_prompt(context: str, question: str) -> str:
    return f"{context}\n\nQuestion:\n{_question_prompt(question)}"


def extract_final_answer(raw_answer: str) -> str:
    lines = raw_answer.splitlines()
    while lines and not lines[-1].strip():
        lines.pop()
    if not lines:
        raise PipelineError(
            f"QA response must end with a non-empty '{FINAL_ANSWER_PREFIX} ...' line."
        )
    final_line = lines[-1].strip()
    if not final_line.startswith(FINAL_ANSWER_PREFIX):
        raise PipelineError(
            f"QA response must end with a non-empty '{FINAL_ANSWER_PREFIX} ...' line."
        )
    final_answer = final_line[len(FINAL_ANSWER_PREFIX) :].strip()
    if not final_answer:
        raise PipelineError(
            f"QA response must end with a non-empty '{FINAL_ANSWER_PREFIX} ...' line."
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
    endpoint=lambda: f"{_cosmos_base_url()}/chat/completions",
    build_payload=None,
)
QA_BACKENDS = {
    backend.model: backend
    for backend in (GEMINI_BACKEND, QWEN_BACKEND, KIMI_BACKEND, COSMOS_BACKEND)
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
    work_title_prefix: bool | None = None,
) -> tuple[Any, ...]:
    key = (input_mode, question_id, model, thinking_effort)
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
    cosmos_served_model_id: str | None = None,
    cosmos_max_tokens: int = DEFAULT_COSMOS_MAX_TOKENS,
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
        elif qa_model == COSMOS_QA_MODEL:
            video_input = _cosmos_video_uri(video_path)
        else:
            video_input = backend.encode_video(video_path)
    elif input_mode == "description":
        if context_text is None:
            raise PipelineError("Description input requires context text.")
        video_input = None
    elif input_mode == "question_only":
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
            )
        elif input_mode == "description":
            prompt_text = _description_prompt(context_text, question["text_en"])
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
                if qa_model == COSMOS_QA_MODEL:
                    if cosmos_served_model_id is None:
                        raise PipelineError("Cosmos3-Nano served model ID is missing.")
                    payload = _cosmos_payload(
                        prompt_text=prompt_text,
                        video_uri=video_input,
                        thinking_effort=thinking_effort,
                        served_model_id=cosmos_served_model_id,
                        max_tokens=cosmos_max_tokens,
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
            if qa_model == COSMOS_QA_MODEL:
                choices = response.get("choices")
                if (
                    isinstance(choices, list)
                    and choices
                    and isinstance(choices[0], dict)
                    and choices[0].get("finish_reason") == "length"
                ):
                    raise PipelineError(
                        "Cosmos3-Nano answer was truncated at max_tokens; "
                        "increase --cosmos-max-tokens and rerun this QA."
                    )
            raw_answer = backend.extract_answer(response)
            final_answer = extract_final_answer(raw_answer)
        except PipelineError as exc:
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
        if backend.effective_reasoning_effort is not None:
            result["effective_reasoning_effort"] = backend.effective_reasoning_effort
        if isinstance(response.get("usage"), dict):
            result["usage"] = response["usage"]
        results.append(result)
    return results, failures


def _preflight_cosmos_videos(
    args: Any, loaded: list[tuple[Path, dict[str, Any]]]
) -> None:
    if args.input != "video":
        return
    selected_videos = set(args.video_id or [])
    for _, case in loaded:
        for video in case["videos"]:
            if selected_videos and video["video_id"] not in selected_videos:
                continue
            if video_selected(video, args.input, getattr(args, "video_scope", None)):
                path = resolve_video_path(video["local_path"], must_exist=True)
                _cosmos_video_uri(path)


def _cosmos_served_model_id(timeout: int) -> str:
    response = get_json(
        url=f"{_cosmos_base_url()}/models",
        timeout=min(timeout, 10),
        service="Cosmos3-Nano",
    )
    models = response.get("data")
    if not isinstance(models, list) or not models:
        raise PipelineError("Cosmos3-Nano /models returned no served models.")
    ids = [
        item.get("id")
        for item in models
        if isinstance(item, dict)
        and isinstance(item.get("id"), str)
        and item["id"].strip()
    ]
    if len(ids) != len(models):
        raise PipelineError("Cosmos3-Nano /models returned an invalid model ID.")
    if COSMOS_QA_MODEL in ids:
        return COSMOS_QA_MODEL
    if len(ids) == 1:
        return ids[0]
    raise PipelineError(
        "Cosmos3-Nano /models returned multiple models without a unique "
        f"{COSMOS_QA_MODEL} entry: {', '.join(ids)}."
    )


def preflight_qa_backend(
    args: Any, loaded: list[tuple[Path, dict[str, Any]]] | None = None
) -> str | None:
    backend = get_backend(args.qa_model)
    expand_thinking_efforts(args.thinking_effort, args.qa_model)
    if args.qa_model == QWEN_QA_MODEL:
        _require_dashscope_sdk()
    backend.require_api_key()
    if args.qa_model == COSMOS_QA_MODEL:
        if loaded is not None:
            _preflight_cosmos_videos(args, loaded)
        return _cosmos_served_model_id(args.timeout)
    return None


def command_qa(args: Any, *, cosmos_served_model_id: str | None = None) -> int:
    backend = get_backend(args.qa_model)
    if args.qa_model == QWEN_QA_MODEL:
        _require_dashscope_sdk()
    api_key = backend.require_api_key()
    request_limiter = (
        RequestLimiter(args.cosmos_workers)
        if args.qa_model == COSMOS_QA_MODEL
        else make_request_limiter(args)
    )
    if args.qa_model == COSMOS_QA_MODEL and cosmos_served_model_id is None:
        cosmos_served_model_id = _cosmos_served_model_id(args.timeout)
    selected_videos = set(args.video_id or [])
    selected_questions = set(args.question_id or [])
    efforts = expand_thinking_efforts(args.thinking_effort, args.qa_model)
    prefix_condition = work_title_prefix_condition(
        args.group,
        args.input,
        args.with_work_title_prefix,
    )
    dataset_dir = grouped_dir(args.dataset_dir, args.group)
    case_paths = iter_case_paths(dataset_dir, args.case_id)
    completed = 0
    failures = 0

    def run_case(case_path: Path) -> tuple[int, int]:
        case = load_case(case_path)
        require_writable_case(case, case_path)
        if args.input == "question_only":
            questions = require_question_only_compatible(case)
            selected = [
                question
                for question in questions
                if not selected_questions
                or question["question_id"] in selected_questions
            ]
            missing_questions = selected_questions - {
                question["question_id"] for question in selected
            }
            if missing_questions:
                raise PipelineError(
                    f"Question IDs not found in {case['case_id']}: "
                    f"{', '.join(sorted(missing_questions))}"
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
                    cosmos_served_model_id=cosmos_served_model_id,
                    cosmos_max_tokens=args.cosmos_max_tokens,
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
        if args.input == "description" and selected_videos:
            conflict_ids = {
                video["video_id"]
                for video in case["videos"]
                if video["role"] == "conflict"
            }
            missing = selected_videos - conflict_ids
            if missing:
                raise PipelineError(
                    f"Conflict video IDs not found in {case['case_id']}: "
                    f"{', '.join(sorted(missing))}"
                )
        for video in case["videos"]:
            if selected_videos and video["video_id"] not in selected_videos:
                continue
            if not video_selected(video, args.input, getattr(args, "video_scope", None)):
                continue
            path: Path | None = None
            context_text: str | None = None
            if args.input == "description":
                if video["role"] != "conflict":
                    continue
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
                context_text = description["context_en"]
            else:
                if video["status"] != "ready":
                    continue
                observed_summary(video)  # Blocks stale annotations after regeneration.
                path = resolve_video_path(video["local_path"], must_exist=True)
            context = video_case_context(case, video)
            if not context["questions"]:
                raise PipelineError(
                    f"Case {case['case_id']} has no questions. Run questions first."
                )
            questions = [
                question
                for question in context["questions"]
                if not selected_questions or question["question_id"] in selected_questions
            ]
            missing_questions = selected_questions - {
                question["question_id"] for question in questions
            }
            if missing_questions:
                raise PipelineError(
                    f"Question IDs not found in {case['case_id']}: "
                    f"{', '.join(sorted(missing_questions))}"
                )

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
                if qa_run_key(
                    args.input,
                    question["question_id"],
                    args.qa_model,
                    effort,
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
                case, job["video"], q, args.input, prefix_condition) for q, _ in job["pending"]}
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
                cosmos_served_model_id=cosmos_served_model_id,
                cosmos_max_tokens=args.cosmos_max_tokens,
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
