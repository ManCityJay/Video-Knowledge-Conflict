"""File-bound visual evidence and qualified references for variant authoring."""
from __future__ import annotations

import base64
import hashlib
import io
from pathlib import Path
from typing import Any

from .core import PipelineError, load_case, resolve_video_path, sha256_text
from .settings import DEFAULT_CASE_DIR


def video_sha256(video: dict[str, Any]) -> str:
    path = resolve_video_path(video['local_path'])
    try:
        with path.open('rb') as stream:
            digest = hashlib.sha256()
            for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError as exc:
        raise PipelineError(f'Cannot read evidence video: {path}') from exc


def observed_summary(video: dict[str, Any]) -> str | None:
    """Never silently reuse an observation of a replaced video."""
    observation = video.get('video_observation')
    if observation is None:
        if video.get('require_video_observation') and video['status'] == 'ready':
            raise PipelineError(f"Review the generated pixels before annotations: {video['video_id']}")
        return None
    if video['status'] != 'ready':
        raise PipelineError('Visual observations are only valid for a ready video.')
    if observation.get('source_sha256') != video_sha256(video):
        raise PipelineError(f"Video changed since visual review: {video['video_id']}")
    summary = observation.get('summary_en')
    if not isinstance(summary, str) or not summary.strip():
        raise PipelineError('A visual observation needs a nonempty summary_en.')
    return summary


def description_source_hash(video: dict[str, Any]) -> str:
    description = video.get('description') or {}
    if description.get('source') == 'video':
        if observed_summary(video) is None:
            raise PipelineError('A video-derived description requires a visual observation.')
        return video_sha256(video)
    if video.get('video_observation') or (video.get('require_video_observation') and video['status'] == 'ready'):
        raise PipelineError('This generated video needs a description derived from reviewed pixels, not its intended prompt.')
    return sha256_text(video['seedance_prompt_en'])


def reference_frames(path: Path, count: int = 6) -> str:
    """A chronological contact sheet supplies actual pixels, not only the prompt."""
    try:
        import av
        from PIL import Image, ImageDraw
        with av.open(str(path)) as container:
            stream = container.streams.video[0]
            if not stream.frames:
                raise PipelineError(f'No frame count for qualified reference: {path}')
            wanted = {round(i * (stream.frames - 1) / (count - 1)) for i in range(count)}
            frames = []
            for index, frame in enumerate(container.decode(video=0)):
                if index in wanted:
                    im = frame.to_image()
                    im.thumbnail((640, 360))
                    frames.append((frame.time, im))
        if len(frames) != count:
            raise PipelineError(f'Could not decode qualified reference: {path}')
        sheet = Image.new('RGB', (1920, 800), 'white')
        draw = ImageDraw.Draw(sheet)
        for i, (time, im) in enumerate(frames):
            x, y = i % 3 * 640, i // 3 * 400
            sheet.paste(im, (x, y + 40))
            draw.text((x + 8, y + 8), f'{time:.3f}s', fill='black')
        buffer = io.BytesIO()
        sheet.save(buffer, format='JPEG', quality=90)
        return 'data:image/jpeg;base64,' + base64.b64encode(buffer.getvalue()).decode('ascii')
    except ImportError as exc:
        raise PipelineError('Qualified video references require PyAV and Pillow.') from exc


def qualified_references(group: str, case_id: str, *, root: Path | None = None) -> list[dict[str, Any]]:
    case_path = (root or DEFAULT_CASE_DIR) / group / (case_id + '.json')
    if not case_path.exists():
        return []
    case = load_case(case_path)
    candidates = [v for v in case['videos'] if v['role'] == 'conflict'
                  and v['status'] == 'ready' and v['human_review'] == 'verified'
                  and 'qualified' in Path(v['local_path']).parts
                  and resolve_video_path(v['local_path']).is_file()]
    # Prefer the tested image-conditioned expansion over an older text-only draft.
    candidates.sort(key=lambda v: (bool(v.get('first_frame_path')), v['video_id']), reverse=True)
    return [{
        'case_id': case_id,
        'observed_video_content_en': observed_summary(v),
        'video_id': v['video_id'],
        'local_path': v['local_path'],
        'video_sha256': video_sha256(v),
        'seedance_prompt_en': v['seedance_prompt_en'],
        'first_frame_path': v.get('first_frame_path'),
        'chronological_frames': reference_frames(resolve_video_path(v['local_path'])),
    } for v in candidates[:2]]
