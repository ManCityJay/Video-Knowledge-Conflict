"""Atomic text/JSON persistence and validated case loading."""
from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from .common import PipelineError
from .schema import validate_case


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(text, encoding="utf-8", newline="\n")
        temporary.replace(path)
    except OSError as exc:
        raise PipelineError(f"Could not write {path}: {exc}") from exc
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass


def atomic_write_json(path: Path, value: Any) -> None:
    atomic_write_text(
        path,
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
    )


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise PipelineError(f"Could not read {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise PipelineError(f"Invalid JSON in {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise PipelineError(f"Expected a JSON object in {path}.")
    return value


def load_case(path: Path) -> dict[str, Any]:
    case = read_json(path)
    try:
        validate_case(case)
    except PipelineError as exc:
        raise PipelineError(f"{path}: {exc}") from exc
    if path.stem != case["case_id"]:
        raise PipelineError(
            f"{path}: filename must match case_id ({case['case_id']}.json)."
        )
    return case
