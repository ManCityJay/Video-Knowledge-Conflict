"""Video QA backends and bounded parallel execution."""

from __future__ import annotations

import base64
import hashlib
import os
import sys
import uuid
from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any, Callable, Iterable

from .core import (
    PipelineError,
    atomic_write_json,
    grouped_dir,
    iter_case_paths,
    load_case,
    resolve_video_path,
    utc_now,
)
from .settings import GEMINI_QA_MODEL, KIMI_QA_MODEL, QWEN_QA_MODEL
from .transport import (
    OPENROUTER_URL,
    RequestLimiter,
    TransportError,
    extract_response_text,
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
    api_key_variable: str
    service: str
    endpoint: EndpointResolver | None
    build_payload: PayloadBuilder | None
    max_body_bytes: int | None = None
    effective_reasoning_effort: str | None = None

    def require_api_key(self) -> str:
        return require_api_key(self.api_key_variable)

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
    question: str,
    video_uri: str,
    thinking_effort: str | None,
    api_key: str,
    timeout: int,
) -> dict[str, Any]:
    if thinking_effort not in (None, "default"):
        raise PipelineError("Qwen thinking effort must be none or default.")
    dashscope = _require_dashscope_sdk()
    dashscope.base_http_api_url = _dashscope_base_http_api_url()
    messages = [
        {
            "role": "user",
            "content": [
                {"video": video_uri, "fps": 2},
                {"text": question},
            ],
        }
    ]
    try:
        response = dashscope.MultiModalConversation.call(
            api_key=api_key,
            model=QWEN_QA_MODEL,
            messages=messages,
            temperature=0.0,
            enable_thinking=thinking_effort is not None,
            timeout=timeout,
        )
    except Exception as exc:
        raise TransportError(
            f"Qwen request failed: {redact(str(exc), api_key)}"
        ) from exc
    return _normalize_dashscope_response(response)


def _gemini_payload(
    question: str,
    video_data_url: str,
    thinking_effort: str | None,
) -> dict[str, Any]:
    if thinking_effort not in ("low", "medium", "high"):
        raise PipelineError("Gemini thinking effort must be low, medium, or high.")
    return {
        "model": GEMINI_QA_MODEL,
        "temperature": 0.0,
        "reasoning": {"effort": thinking_effort},
        "stream": False,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": question},
                    {"type": "video_url", "video_url": {"url": video_data_url}},
                ],
            }
        ],
    }


def _kimi_payload(
    question: str,
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
                    {"type": "text", "text": question},
                ],
            }
        ],
    }


GEMINI_BACKEND = QABackend(
    model=GEMINI_QA_MODEL,
    thinking_efforts=("low", "medium", "high"),
    default_thinking_effort="medium",
    temperature=0.0,
    api_key_variable="OPENROUTER_API_KEY",
    service="OpenRouter",
    endpoint=lambda: OPENROUTER_URL,
    build_payload=_gemini_payload,
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
QA_BACKENDS = {
    backend.model: backend
    for backend in (GEMINI_BACKEND, QWEN_BACKEND, KIMI_BACKEND)
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


def selected_thinking_efforts(
    values: Iterable[str] | None,
) -> set[str | None] | None:
    requested = list(values or [])
    if not requested or "all" in requested:
        return None
    return {normalize_thinking_effort(value) for value in requested}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise PipelineError(f"Could not hash video file {path}: {exc}") from exc
    return digest.hexdigest()


def qa_result_key(result: dict[str, Any]) -> tuple[Any, ...]:
    return (
        result.get("video_sha256"),
        result.get("question_id"),
        result.get("question"),
        result.get("model"),
        result.get("thinking_effort"),
    )


def run_video_qa_batch(
    *,
    video_path: Path,
    video_hash: str,
    question_runs: list[tuple[dict[str, Any], str | None]],
    qa_model: str,
    api_key: str,
    timeout: int,
    max_retries: int,
    request_limiter: RequestLimiter,
) -> list[dict[str, Any]]:
    backend = get_backend(qa_model)
    video_input = (
        _qwen_video_uri(video_path)
        if qa_model == QWEN_QA_MODEL
        else backend.encode_video(video_path)
    )
    results: list[dict[str, Any]] = []
    for question, thinking_effort in question_runs:
        if qa_model == QWEN_QA_MODEL:
            response = send_with_retry(
                lambda question=question, thinking_effort=thinking_effort: (
                    _send_qwen_request(
                        question=question["text_en"],
                        video_uri=video_input,
                        thinking_effort=thinking_effort,
                        api_key=api_key,
                        timeout=timeout,
                    )
                ),
                request_limiter=request_limiter,
                max_retries=max_retries,
            )
        else:
            if backend.build_payload is None:
                raise PipelineError(
                    f"{backend.service} does not use a Base64 payload builder."
                )
            payload = backend.build_payload(
                question["text_en"], video_input, thinking_effort
            )
            response = send_with_retry(
                lambda payload=payload: backend.send_request(payload, api_key, timeout),
                request_limiter=request_limiter,
                max_retries=max_retries,
            )
        result: dict[str, Any] = {
            "run_id": uuid.uuid4().hex,
            "timestamp": utc_now(),
            "video_sha256": video_hash,
            "question_id": question["question_id"],
            "question": question["text_en"],
            "raw_answer": backend.extract_answer(response),
            "model": qa_model,
            "thinking_effort": thinking_effort,
            "temperature": backend.temperature,
            "request_id": response.get("id"),
            "judgment": None,
        }
        if backend.effective_reasoning_effort is not None:
            result["effective_reasoning_effort"] = backend.effective_reasoning_effort
        if isinstance(response.get("usage"), dict):
            result["usage"] = response["usage"]
        results.append(result)
    return results


def command_qa(args: Any) -> int:
    backend = get_backend(args.qa_model)
    if args.qa_model == QWEN_QA_MODEL:
        _require_dashscope_sdk()
    api_key = backend.require_api_key()
    request_limiter = make_request_limiter(args)
    selected_videos = set(args.video_id or [])
    selected_questions = set(args.question_id or [])
    efforts = expand_thinking_efforts(args.thinking_effort, args.qa_model)
    dataset_dir = grouped_dir(args.dataset_dir, args.group)
    case_paths = iter_case_paths(dataset_dir, args.case_id)
    completed = 0
    failures = 0

    def run_case(case_path: Path) -> tuple[int, int]:
        case = load_case(case_path)
        if not case["questions"]:
            raise PipelineError(
                f"Case {case['case_id']} has no questions. Run questions first."
            )
        questions = [
            question
            for question in case["questions"]
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

        jobs: list[tuple[dict[str, Any], Path, str, list[Any]]] = []
        for video in case["videos"]:
            if selected_videos and video["video_id"] not in selected_videos:
                continue
            if video["status"] != "ready":
                continue
            path = resolve_video_path(video["local_path"], must_exist=True)
            video_hash = sha256_file(path)
            existing = {qa_result_key(result) for result in video["qa_results"]}
            pending = [
                (question, effort)
                for effort in efforts
                for question in questions
                if args.force
                or (
                    video_hash,
                    question["question_id"],
                    question["text_en"],
                    args.qa_model,
                    effort,
                )
                not in existing
            ]
            if pending:
                jobs.append((video, path, video_hash, pending))

        if not jobs:
            return 0, 0

        def run(job: tuple[dict[str, Any], Path, str, list[Any]]) -> list[dict[str, Any]]:
            _, path, video_hash, pending = job
            return run_video_qa_batch(
                video_path=path,
                video_hash=video_hash,
                question_runs=pending,
                qa_model=args.qa_model,
                api_key=api_key,
                timeout=args.timeout,
                max_retries=args.max_retries,
                request_limiter=request_limiter,
            )

        case_completed = 0
        case_failures = 0
        with ThreadPoolExecutor(max_workers=min(args.qa_workers, len(jobs))) as executor:
            futures = {executor.submit(run, job): job[0] for job in jobs}
            for future in as_completed(futures):
                video = futures[future]
                try:
                    results = future.result()
                except PipelineError as exc:
                    case_failures += 1
                    print(
                        f"Error in QA {case['case_id']}/{video['video_id']}: {exc}",
                        file=sys.stderr,
                    )
                    continue
                video["qa_results"].extend(results)
                atomic_write_json(case_path, case)
                case_completed += len(results)
                print(
                    f"QA {case['case_id']}/{video['video_id']}: "
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
