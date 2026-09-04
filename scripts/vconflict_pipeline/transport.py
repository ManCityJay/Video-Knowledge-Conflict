"""HTTP transport, throttling, retries, and credential-safe errors."""

from __future__ import annotations

import argparse
import json
import os
import random
import threading
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Callable, TypeVar
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .core import PipelineError

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
T = TypeVar("T")


class TransportError(PipelineError):
    """A user-facing provider or network error."""

    def __init__(self, message: str, *, retry_after: float | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class RequestLimiter:
    """Bound concurrent calls and optionally pace their start times."""

    def __init__(self, max_concurrent: int, requests_per_minute: float = 0) -> None:
        self._semaphore = threading.BoundedSemaphore(max_concurrent)
        self._interval = 60.0 / requests_per_minute if requests_per_minute else 0.0
        self._pace_lock = threading.Lock()
        self._next_start = 0.0

    def call(self, callback: Callable[[], T]) -> T:
        with self._semaphore:
            delay = 0.0
            if self._interval:
                with self._pace_lock:
                    now = time.monotonic()
                    delay = max(0.0, self._next_start - now)
                    self._next_start = max(now, self._next_start) + self._interval
            if delay:
                time.sleep(delay)
            return callback()


def make_request_limiter(args: argparse.Namespace) -> RequestLimiter:
    return RequestLimiter(args.openrouter_workers, args.openrouter_rpm)


# The historical flag names remain part of the stage CLI.
make_openrouter_limiter = make_request_limiter


def require_api_key(variable: str) -> str:
    value = os.environ.get(variable, "").strip()
    if not value:
        raise PipelineError(f"Set the {variable} environment variable.")
    return value


def require_openrouter_api_key() -> str:
    return require_api_key("OPENROUTER_API_KEY")


def redact(value: str, secret: str) -> str:
    return value.replace(secret, "[REDACTED]") if secret else value


def _retry_after_seconds(error: HTTPError) -> float | None:
    raw = error.headers.get("Retry-After") if error.headers else None
    if not raw:
        return None
    try:
        return max(0.0, float(raw))
    except ValueError:
        try:
            retry_at = parsedate_to_datetime(raw)
        except (TypeError, ValueError, OverflowError):
            return None
        if retry_at.tzinfo is None:
            retry_at = retry_at.replace(tzinfo=timezone.utc)
        return max(0.0, (retry_at - datetime.now(timezone.utc)).total_seconds())


def _http_error_message(error: HTTPError, secret: str) -> str:
    message: Any = error.reason or "Request failed"
    try:
        decoded = json.loads(error.read().decode("utf-8"))
        if isinstance(decoded, dict):
            detail = decoded.get("error")
            if isinstance(detail, dict) and isinstance(detail.get("message"), str):
                message = detail["message"]
            elif isinstance(detail, str):
                message = detail
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        pass
    return redact(str(message), secret)


def post_json(
    *,
    url: str,
    payload: dict[str, Any],
    api_key: str,
    timeout: int,
    service: str,
    max_body_bytes: int | None = None,
) -> dict[str, Any]:
    """POST JSON to an HTTPS endpoint and return an object response."""
    if not url.startswith("https://"):
        raise TransportError(f"{service} base URL must use HTTPS.")
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    if max_body_bytes is not None and len(body) > max_body_bytes:
        raise TransportError(
            f"{service} request body is too large ({len(body)} bytes; "
            f"maximum {max_body_bytes} bytes)."
        )
    request = Request(
        url,
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout) as response:  # nosec B310
            response_body = response.read().decode("utf-8")
    except HTTPError as exc:
        raise TransportError(
            f"{service} request failed (HTTP {exc.code}): "
            f"{_http_error_message(exc, api_key)}",
            retry_after=_retry_after_seconds(exc),
        ) from exc
    except URLError as exc:
        raise TransportError(
            f"Could not reach {service}: {redact(str(exc.reason), api_key)}"
        ) from exc
    except TimeoutError as exc:
        raise TransportError(f"{service} request timed out.") from exc
    except OSError as exc:
        raise TransportError(
            f"{service} request failed: {redact(str(exc), api_key)}"
        ) from exc

    try:
        decoded = json.loads(response_body)
    except json.JSONDecodeError as exc:
        raise TransportError(f"{service} returned invalid JSON.") from exc
    if not isinstance(decoded, dict):
        raise TransportError(f"{service} returned invalid JSON.")
    return decoded


def extract_response_text(response: dict[str, Any], service: str) -> str:
    """Extract final assistant text without including reasoning content."""
    choices = response.get("choices")
    if not isinstance(choices, list) or not choices:
        raise TransportError(f"{service} response did not contain an answer choice.")
    first = choices[0]
    message = first.get("message") if isinstance(first, dict) else None
    if not isinstance(message, dict):
        raise TransportError(f"{service} response did not contain a message.")
    content = message.get("content")
    if isinstance(content, str) and content.strip():
        return content
    if isinstance(content, list):
        parts = [
            part["text"]
            for part in content
            if isinstance(part, dict)
            and part.get("type") == "text"
            and isinstance(part.get("text"), str)
        ]
        answer = "".join(parts)
        if answer.strip():
            return answer
    raise TransportError(f"{service} response did not contain textual content.")


def _is_retryable(error: Exception) -> bool:
    message = str(error).lower()
    return any(
        marker in message
        for marker in (
            "http 429",
            "http 502",
            "http 503",
            "timed out",
            "timeout",
            "temporarily unavailable",
            "overloaded",
        )
    )


def send_with_retry(
    callback: Callable[[], dict[str, Any]],
    *,
    request_limiter: RequestLimiter | None,
    max_retries: int,
) -> dict[str, Any]:
    for attempt in range(max_retries + 1):
        try:
            return (
                callback()
                if request_limiter is None
                else request_limiter.call(callback)
            )
        except TransportError as exc:
            if attempt >= max_retries or not _is_retryable(exc):
                raise
            delay = min(30.0, 2.0**attempt) + random.uniform(0, 0.5)
            if exc.retry_after is not None:
                delay = max(delay, exc.retry_after)
            time.sleep(delay)
    raise AssertionError("unreachable")


def send_openrouter_with_retry(
    payload: dict[str, Any],
    request_limiter: RequestLimiter | None = None,
    *,
    api_key: str,
    timeout: int,
    max_retries: int,
) -> dict[str, Any]:
    return send_with_retry(
        lambda: post_json(
            url=OPENROUTER_URL,
            payload=payload,
            api_key=api_key,
            timeout=timeout,
            service="OpenRouter",
        ),
        request_limiter=request_limiter,
        max_retries=max_retries,
    )


def openrouter_json(
    *,
    messages: list[dict[str, Any]],
    model: str,
    schema_name: str,
    schema: dict[str, Any],
    api_key: str,
    timeout: int,
    max_retries: int = 4,
    request_limiter: RequestLimiter | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    payload = {
        "model": model,
        "stream": False,
        "messages": messages,
        "response_format": {
            "type": "json_schema",
            "json_schema": {"name": schema_name, "strict": True, "schema": schema},
        },
        "provider": {"require_parameters": True},
    }
    response = send_openrouter_with_retry(
        payload,
        request_limiter,
        api_key=api_key,
        timeout=timeout,
        max_retries=max_retries,
    )
    try:
        parsed = json.loads(extract_response_text(response, "OpenRouter"))
    except json.JSONDecodeError as exc:
        raise PipelineError("OpenRouter structured response was not valid JSON.") from exc
    if not isinstance(parsed, dict):
        raise PipelineError("OpenRouter structured response must be an object.")
    return parsed, response
