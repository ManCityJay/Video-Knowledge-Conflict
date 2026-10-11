"""Project path validation and source/case discovery."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable

from .common import PipelineError, validate_group, validate_id
from .settings import PROJECT_ROOT, VIDEO_EXTENSIONS


SOURCE_CASE_HEADING = re.compile(
    r"^###\s+(?:(?P<legacy_number>\d+(?:\.\d+)*)\s+)?(?P<title>.+?)\s*$"
)


def _is_within(child: Path, parent: Path) -> bool:
    try:
        child.relative_to(parent)
    except ValueError:
        return False
    return True


def grouped_dir(root: Path, group: str | None) -> Path:
    return root if group is None else root / validate_group(group)


def resolve_video_path(
    local_path: str, must_exist: bool = False, *, project_root: Path | None = None,
) -> Path:
    root = PROJECT_ROOT if project_root is None else project_root
    supplied = Path(local_path)
    if supplied.is_absolute():
        raise PipelineError("Video local_path must be relative to the project root.")
    candidate = (root / supplied).resolve(strict=False)
    video_root = (root / "videos" / "seedance").resolve(strict=False)
    if not _is_within(candidate, video_root):
        raise PipelineError("Video local_path must stay within videos/seedance.")
    if candidate.suffix.lower() not in VIDEO_EXTENSIONS:
        raise PipelineError(f"Unsupported video extension in local_path: {local_path}")
    if must_exist and (not candidate.exists() or not candidate.is_file()):
        raise PipelineError(f"Video file was not found: {local_path}")
    return candidate


def parse_source_case(path: Path) -> dict[str, str]:
    try:
        content = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise PipelineError(f"Could not read source case {path}: {exc}") from exc
    first_line = content.splitlines()[0] if content.splitlines() else ""
    heading = SOURCE_CASE_HEADING.match(first_line)
    if not heading:
        raise PipelineError(f"Source case must start with a level-three heading: {path}")
    title = heading.group("title").strip()
    case_id = validate_id(path.stem, "source filename")
    return {
        "case_id": case_id,
        "title": title,
        "content": content,
    }


def iter_source_paths(
    source_dir: Path,
    case_ids: Iterable[str] | None = None,
) -> list[Path]:
    selected = set(case_ids or [])
    if not source_dir.exists():
        raise PipelineError(f"Source case directory was not found: {source_dir}")
    paths = sorted(source_dir.glob("*.md"))
    if selected:
        paths = [path for path in paths if path.stem in selected]
        missing = selected - {path.stem for path in paths}
        if missing:
            raise PipelineError(f"Source cases were not found: {', '.join(sorted(missing))}")
    if not paths:
        raise PipelineError(f"No source case Markdown files were found in {source_dir}.")
    return paths


def iter_case_paths(
    dataset_dir: Path,
    case_ids: Iterable[str] | None = None,
) -> list[Path]:
    selected = set(case_ids or [])
    if not dataset_dir.exists():
        raise PipelineError(f"Dataset directory was not found: {dataset_dir}")
    paths = sorted(dataset_dir.glob("*.json"))
    if selected:
        paths = [path for path in paths if path.stem in selected]
        missing = selected - {path.stem for path in paths}
        if missing:
            raise PipelineError(f"Case files were not found: {', '.join(sorted(missing))}")
    if not paths:
        raise PipelineError(f"No case JSON files were found in {dataset_dir}.")
    return paths
