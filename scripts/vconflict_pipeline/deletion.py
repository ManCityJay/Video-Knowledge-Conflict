"""Delete videos, questions, or complete cases from the local dataset."""

from __future__ import annotations

import argparse
import copy
import shutil
import sys
from pathlib import Path
from typing import Any, Iterable

from .core import (
    PipelineError,
    atomic_write_json,
    grouped_dir,
    load_case,
    resolve_video_path,
    validate_case,
)
from .settings import PROJECT_ROOT


def _unique(values: Iterable[str] | None) -> set[str]:
    return set(values or [])


def _missing(requested: set[str], available: Iterable[str]) -> set[str]:
    return requested - set(available)


def _validated_local_video_path(local_path: str) -> Path:
    resolve_video_path(local_path)
    return PROJECT_ROOT / Path(local_path)


def _remove_selected(
    *,
    case_path: Path,
    case: dict[str, Any],
    video_ids: set[str],
    question_ids: set[str],
) -> int:
    videos_by_id = {video["video_id"]: video for video in case["videos"]}
    missing_videos = _missing(video_ids, videos_by_id)
    if missing_videos:
        raise PipelineError(
            f"Video IDs not found in {case['case_id']}: "
            f"{', '.join(sorted(missing_videos))}"
        )

    questions_by_id = {
        question["question_id"]: question for question in case["questions"]
    }
    missing_questions = _missing(question_ids, questions_by_id)
    if missing_questions:
        raise PipelineError(
            f"Question IDs not found in {case['case_id']}: "
            f"{', '.join(sorted(missing_questions))}"
        )

    selected_videos = [videos_by_id[video_id] for video_id in video_ids]
    control_ids = sorted(
        video["video_id"]
        for video in selected_videos
        if video["role"] == "control"
    )
    if control_ids:
        raise PipelineError(
            "Control videos cannot be deleted individually: "
            f"{', '.join(control_ids)}. Delete the entire case instead."
        )
    remaining_conflicts = sum(
        video["role"] == "conflict" and video["video_id"] not in video_ids
        for video in case["videos"]
    )
    if remaining_conflicts < 1:
        raise PipelineError(
            "At least one conflict video must remain. Delete the entire case instead."
        )

    video_paths = [
        _validated_local_video_path(video["local_path"])
        for video in selected_videos
    ]
    removed_results = [
        result
        for video in case["videos"]
        for result in video["qa_results"]
        if video["video_id"] in video_ids
        or result["question_id"] in question_ids
    ]
    removed_judgments = sum(
        isinstance(result.get("judgment"), dict) for result in removed_results
    )
    removed_descriptions = sum(
        isinstance(video.get("description"), dict) for video in selected_videos
    )

    updated = copy.deepcopy(case)
    updated["videos"] = [
        video for video in updated["videos"] if video["video_id"] not in video_ids
    ]
    updated["questions"] = [
        question
        for question in updated["questions"]
        if question["question_id"] not in question_ids
    ]
    for video in updated["videos"]:
        video["qa_results"] = [
            result
            for result in video["qa_results"]
            if result["question_id"] not in question_ids
        ]
    validate_case(updated)
    atomic_write_json(case_path, updated)

    deleted_files = 0
    missing_files = 0
    cleanup_failures = 0
    for video_path in video_paths:
        if not video_path.exists() and not video_path.is_symlink():
            missing_files += 1
            continue
        try:
            video_path.unlink()
        except OSError as exc:
            cleanup_failures += 1
            print(
                f"Error deleting local video {video_path}: {exc}",
                file=sys.stderr,
            )
        else:
            deleted_files += 1

    print(
        f"Deleted from case {case['case_id']}: {len(video_ids)} video(s), "
        f"{len(question_ids)} question(s), {len(removed_descriptions)} "
        f"description(s), {len(removed_results)} QA result(s), and "
        f"{removed_judgments} judgment(s)."
    )
    if video_paths:
        print(
            f"Local videos: deleted {deleted_files}; already missing "
            f"{missing_files}; failed {cleanup_failures}."
        )
    print("Derived summaries and reports are stale; rerun summarize.")
    return 1 if cleanup_failures else 0


def _case_video_directories(case: dict[str, Any]) -> list[Path]:
    directories: set[Path] = set()
    for video in case["videos"]:
        local_path = _validated_local_video_path(video["local_path"])
        directories.add(local_path.parent)
    return sorted(directories, key=str)


def _remove_entire_case(
    *,
    case_path: Path,
    case: dict[str, Any],
    video_directories: list[Path],
) -> int:
    try:
        case_path.unlink()
    except OSError as exc:
        raise PipelineError(f"Could not delete case JSON {case_path}: {exc}") from exc

    deleted_directories = 0
    missing_directories = 0
    cleanup_failures = 0
    for directory in video_directories:
        if not directory.exists() and not directory.is_symlink():
            missing_directories += 1
            continue
        try:
            if directory.is_symlink():
                directory.unlink()
            else:
                shutil.rmtree(directory)
        except OSError as exc:
            cleanup_failures += 1
            print(
                f"Error deleting case video directory {directory}: {exc}",
                file=sys.stderr,
            )
        else:
            deleted_directories += 1

    print(f"Deleted case JSON: {case_path}")
    print(
        f"Case video directories: deleted {deleted_directories}; already missing "
        f"{missing_directories}; failed {cleanup_failures}."
    )
    print(
        "Source Markdown and derived results were not deleted; existing summaries "
        "and reports are stale."
    )
    return 1 if cleanup_failures else 0


def _load_selected_cases(
    dataset_dir: Path,
    case_ids: Iterable[str],
) -> list[tuple[Path, dict[str, Any]]]:
    unique_case_ids = list(dict.fromkeys(case_ids))
    case_paths = [dataset_dir / f"{case_id}.json" for case_id in unique_case_ids]
    missing_paths = [path for path in case_paths if not path.exists()]
    if missing_paths:
        raise PipelineError(
            "Case files were not found: "
            + ", ".join(str(path) for path in missing_paths)
        )
    return [(path, load_case(path)) for path in case_paths]


def command_delete(args: argparse.Namespace) -> int:
    dataset_dir = grouped_dir(args.dataset_dir, args.group)
    loaded = _load_selected_cases(dataset_dir, args.case_id)
    if args.delete_all:
        prepared = [
            (case_path, case, _case_video_directories(case))
            for case_path, case in loaded
        ]
        status = 0
        for case_path, case, video_directories in prepared:
            status |= _remove_entire_case(
                case_path=case_path,
                case=case,
                video_directories=video_directories,
            )
        print(f"Deleted {len(prepared)} complete case(s).")
        return status
    case_path, case = loaded[0]
    return _remove_selected(
        case_path=case_path,
        case=case,
        video_ids=_unique(args.video_id),
        question_ids=_unique(args.question_id),
    )
