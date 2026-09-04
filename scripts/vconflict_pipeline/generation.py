"""Seedance generation, persistence, and human review."""

from __future__ import annotations

import argparse
import copy
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from urllib.request import urlretrieve

from .core import *
from .settings import *
from .transport import RequestLimiter

def to_plain_data(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return to_plain_data(value.model_dump())
    if hasattr(value, "dict"):
        return to_plain_data(value.dict())
    if isinstance(value, dict):
        return {str(key): to_plain_data(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_plain_data(item) for item in value]
    if hasattr(value, "__dict__"):
        return {
            key: to_plain_data(item)
            for key, item in vars(value).items()
            if not key.startswith("_")
        }
    return value


def extract_video_urls(value: Any) -> list[str]:
    data = to_plain_data(value)
    candidates: list[tuple[int, str]] = []

    def walk(obj: Any, path: str = "") -> None:
        if isinstance(obj, dict):
            for key, item in obj.items():
                walk(item, f"{path}.{key}" if path else str(key))
        elif isinstance(obj, list):
            for index, item in enumerate(obj):
                walk(item, f"{path}[{index}]")
        elif isinstance(obj, str) and obj.startswith(("http://", "https://")):
            parsed = urlparse(obj)
            if not parsed.path.lower().endswith(tuple(VIDEO_EXTENSIONS)):
                return
            score = 10 if any(
                token in path.lower()
                for token in ("output", "result", "generated", "video")
            ) else 0
            if any(
                token in path.lower()
                for token in ("input", "reference", "request")
            ):
                score -= 20
            candidates.append((score, obj))

    walk(data)
    result: list[str] = []
    seen: set[str] = set()
    for _, url in sorted(candidates, key=lambda item: item[0], reverse=True):
        if url not in seen:
            seen.add(url)
            result.append(url)
    return result


def object_value(value: Any, name: str, default: Any = None) -> Any:
    return value.get(name, default) if isinstance(value, dict) else getattr(
        value, name, default
    )


def create_ark_client(api_key: str, base_url: str) -> Any:
    try:
        from volcenginesdkarkruntime import Ark
    except ImportError as exc:
        raise PipelineError(
            'Install the Ark SDK first: pip install -U "volcengine-python-sdk[ark]"'
        ) from exc
    return Ark(api_key=api_key, base_url=base_url)


def persist_video_state(
    *,
    case: dict[str, Any],
    case_path: Path,
    video: dict[str, Any],
    lock: threading.Lock,
    **changes: Any,
) -> None:
    with lock:
        video.update(changes)
        atomic_write_json(case_path, case)


def generate_one_video(
    *,
    client: Any,
    case: dict[str, Any],
    case_path: Path,
    video: dict[str, Any],
    args: argparse.Namespace,
    lock: threading.Lock,
) -> str:
    output_path = resolve_video_path(video["local_path"])
    status = video["status"]

    if status == "ready":
        if output_path.exists() and output_path.is_file():
            return "skipped"
        replacement_status = "submitted" if video.get("task_id") else "failed"
        persist_video_state(
            case=case,
            case_path=case_path,
            video=video,
            lock=lock,
            status=replacement_status,
        )
        status = replacement_status

    if status == "failed":
        if not args.retry_failed:
            return "skipped"
        persist_video_state(
            case=case,
            case_path=case_path,
            video=video,
            lock=lock,
            task_id=None,
            status="pending",
        )
        status = "pending"

    if status == "pending":
        try:
            created = client.content_generation.tasks.create(
                model=args.model,
                content=[{"type": "text", "text": video["seedance_prompt_en"]}],
                generate_audio=False,
                ratio=args.ratio,
                resolution=args.resolution,
                duration=args.duration,
                watermark=False,
            )
        except Exception as exc:
            persist_video_state(
                case=case,
                case_path=case_path,
                video=video,
                lock=lock,
                status="failed",
            )
            raise PipelineError(f"Seedance create request failed: {exc}") from exc
        task_id = object_value(created, "id")
        if not isinstance(task_id, str) or not task_id:
            persist_video_state(
                case=case,
                case_path=case_path,
                video=video,
                lock=lock,
                status="failed",
            )
            raise PipelineError("Seedance create response did not contain a task id.")
        persist_video_state(
            case=case,
            case_path=case_path,
            video=video,
            lock=lock,
            task_id=task_id,
            status="submitted",
        )

    task_id = video.get("task_id")
    if not isinstance(task_id, str) or not task_id:
        raise PipelineError("Submitted video has no task_id.")
    final_result: Any = None
    for poll_index in range(1, args.max_polls + 1):
        try:
            final_result = client.content_generation.tasks.get(task_id=task_id)
        except Exception as exc:
            raise PipelineError(
                f"Seedance polling failed; task remains submitted: {task_id}: {exc}"
            ) from exc
        task_status = str(object_value(final_result, "status", "unknown")).lower()
        print(
            f"{case['case_id']}/{video['video_id']} "
            f"[{poll_index}/{args.max_polls}] {task_status}"
        )
        if task_status == "succeeded":
            break
        if task_status == "failed":
            persist_video_state(
                case=case,
                case_path=case_path,
                video=video,
                lock=lock,
                status="failed",
            )
            raise PipelineError(f"Seedance task failed: {task_id}")
        if poll_index == args.max_polls:
            raise PipelineError(
                f"Seedance polling timed out; task remains submitted: {task_id}"
            )
        time.sleep(args.poll_interval)

    urls = extract_video_urls(final_result)
    if not urls:
        persist_video_state(
            case=case,
            case_path=case_path,
            video=video,
            lock=lock,
            status="failed",
        )
        raise PipelineError(f"Seedance task returned no video URL: {task_id}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        urlretrieve(urls[0], output_path)
    except OSError as exc:
        persist_video_state(
            case=case,
            case_path=case_path,
            video=video,
            lock=lock,
            status="submitted",
        )
        raise PipelineError(
            f"Could not download generated video; task remains submitted: {exc}"
        ) from exc
    persist_video_state(
        case=case,
        case_path=case_path,
        video=video,
        lock=lock,
        status="ready",
        human_review="pending",
        qa_results=[],
    )
    return "generated"


def command_generate(args: argparse.Namespace) -> int:
    api_key = os.environ.get("ARK_API_KEY", "").strip()
    if not api_key:
        raise PipelineError("Set the ARK_API_KEY environment variable.")
    selected_videos = set(args.video_id or [])
    dataset_dir = grouped_dir(args.dataset_dir, args.group)
    case_paths = iter_case_paths(dataset_dir, args.case_id)
    seedance_slots = threading.BoundedSemaphore(args.seedance_total_workers)
    failures = 0

    def run_case(case_path: Path) -> int:
        case = load_case(case_path)
        videos = [
            video
            for video in case["videos"]
            if not selected_videos or video["video_id"] in selected_videos
        ]
        if selected_videos:
            missing = selected_videos - {video["video_id"] for video in videos}
            if missing:
                raise PipelineError(
                    f"Video IDs not found in {case['case_id']}: "
                    f"{', '.join(sorted(missing))}"
                )
        lock = threading.Lock()

        def run(video: dict[str, Any]) -> str:
            with seedance_slots:
                client = create_ark_client(api_key, args.base_url)
                return generate_one_video(
                    client=client,
                    case=case,
                    case_path=case_path,
                    video=video,
                    args=args,
                    lock=lock,
                )

        case_failures = 0
        workers = min(args.seedance_workers, len(videos))
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {executor.submit(run, video): video for video in videos}
            for future in as_completed(futures):
                video = futures[future]
                try:
                    result = future.result()
                    print(f"{case['case_id']}/{video['video_id']}: {result}")
                except PipelineError as exc:
                    case_failures += 1
                    print(
                        f"Error generating {case['case_id']}/{video['video_id']}: {exc}",
                        file=sys.stderr,
                    )
        return case_failures

    workers = min(args.case_workers, len(case_paths))
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(run_case, path): path for path in case_paths}
        for future in as_completed(futures):
            case_path = futures[future]
            try:
                failures += future.result()
            except PipelineError as exc:
                failures += 1
                print(f"Error generating case {case_path.stem}: {exc}", file=sys.stderr)
    return 1 if failures else 0


def command_review(args: argparse.Namespace) -> int:
    dataset_dir = grouped_dir(args.dataset_dir, args.group)
    case_path = dataset_dir / f"{args.case_id}.json"
    if not case_path.exists():
        raise PipelineError(f"Case file was not found: {case_path}")
    case = load_case(case_path)
    for video in case["videos"]:
        if video["video_id"] != args.video_id:
            continue
        if video["status"] != "ready":
            raise PipelineError("Only ready videos can be reviewed.")
        resolve_video_path(video["local_path"], must_exist=True)
        video["human_review"] = args.decision
        atomic_write_json(case_path, case)
        print(
            f"Marked {args.case_id}/{args.video_id} as {args.decision}: "
            f"{video['local_path']}"
        )
        return 0
    raise PipelineError(f"Video ID was not found in {args.case_id}: {args.video_id}")

