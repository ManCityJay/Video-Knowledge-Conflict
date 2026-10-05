"""Append rejected QA responses without changing experiment records."""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any

from .settings import PROJECT_ROOT


COSMOS_FORMAT_FAILURES_PATH = (
    PROJECT_ROOT / "artifacts" / "qa_failures" / "cosmos_invalid_final_answer.jsonl"
)
_APPEND_LOCK = threading.Lock()


def append_cosmos_format_failure(record: dict[str, Any]) -> Path:
    """Serialize one JSON line and protect appends across threads and processes."""
    line = (json.dumps(record, ensure_ascii=False) + "\n").encode("utf-8")
    path = COSMOS_FORMAT_FAILURES_PATH
    with _APPEND_LOCK:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a+b") as handle:
            # Windows permits locking a byte beyond EOF, including an empty file.
            # All writers lock byte zero, then seek to EOF only after acquiring it.
            if os.name == "nt":
                import msvcrt

                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                handle.seek(0, os.SEEK_END)
                handle.write(line)
                handle.flush()
                os.fsync(handle.fileno())
            finally:
                if os.name == "nt":
                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    return path
