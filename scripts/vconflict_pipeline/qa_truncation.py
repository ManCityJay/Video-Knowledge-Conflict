"""Preserve token-limited QA responses outside successful experiment results."""
from __future__ import annotations

import json
import re
import sys
import threading
from pathlib import Path
from typing import Any

from .settings import COSMOS_QA_MODEL


def split_truncated_response(response: dict[str, Any], model: str) -> dict[str, Any]:
    choices = response.get("choices")
    choice = choices[0] if isinstance(choices, list) and choices else {}
    message = choice.get("message", {}) if isinstance(choice, dict) else {}
    if not isinstance(message, dict):
        message = {}
    content = message.get("content")
    answer = content if isinstance(content, str) else ""
    if isinstance(content, list):
        answer = "".join(
            part["text"] for part in content
            if isinstance(part, dict) and part.get("type") == "text"
            and isinstance(part.get("text"), str)
        )
    reasoning_fields = [field for field in ("reasoning", "reasoning_content")
                        if isinstance(message.get(field), str)]
    if model != COSMOS_QA_MODEL and reasoning_fields:
        field = next((field for field in reasoning_fields if message[field]), reasoning_fields[0])
        return {"reasoning_text": message[field], "answer_text": answer,
                "reasoning_source": f"message.{field}"}
    if model == COSMOS_QA_MODEL and "<think>" in answer:
        reasoning_parts, answer_parts = [], []
        offset = 0
        unclosed = False
        for match in re.finditer(r"<think>(.*?)(</think>|$)", answer, re.DOTALL):
            answer_parts.append(answer[offset:match.start()])
            reasoning_parts.append(match.group(1))
            unclosed = unclosed or not match.group(2)
            offset = match.end()
        answer_parts.append(answer[offset:])
        return {"reasoning_text": "".join(reasoning_parts),
                "answer_text": "".join(answer_parts),
                "reasoning_source": "content.think_tags_unclosed" if unclosed else "content.think_tags"}
    return {"reasoning_text": None, "answer_text": answer,
            "reasoning_source": "unavailable"}


class MaxTokenLog:
    """One append-only JSONL shared by this command's worker threads."""

    def __init__(self, path: Path) -> None:
        self.path = path.expanduser().resolve()
        self._lock = threading.Lock()
        print(f"Max-token log: {self.path}", flush=True)
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8", newline="\n"):
                pass
        except OSError as exc:
            self._report_error(exc)

    def _report_error(self, exc: Exception) -> None:
        print(f"Max-token log write failed: {self.path}: {exc}", file=sys.stderr, flush=True)

    def append(self, record: dict[str, Any]) -> None:
        with self._lock:
            try:
                line = json.dumps(record, ensure_ascii=False) + "\n"
                self.path.parent.mkdir(parents=True, exist_ok=True)
                with self.path.open("a", encoding="utf-8", newline="\n") as output:
                    output.write(line)
                    output.flush()
            except (OSError, UnicodeError, TypeError, ValueError) as exc:
                # Logging must not replace the truncation error or its count.
                self._report_error(exc)
