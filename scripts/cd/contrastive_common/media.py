"""Native model sampling, cached frames and auditable video preprocessing."""
from __future__ import annotations

import copy
from .video import load_frames, prepare_inputs


def sample_media(media, fps, *, family, processor):
    import numpy as np
    from dataclasses import fields
    from types import SimpleNamespace
    from transformers.video_utils import VideoMetadata
    from vllm.multimodal.video import VideoBackend

    frames, original = media
    metadata = copy.deepcopy(original)
    source_fps = float(metadata['fps'])
    source_indices = list(map(int, metadata['frames_indices']))
    if source_indices != list(range(int(metadata['total_num_frames']))):
        raise ValueError('FPS alignment requires a complete source-frame decode')
    if len(source_indices) != len(frames):
        raise ValueError('Frame metadata does not match decoded video')
    if family == 'gemma':
        # Same function used by the main Gemma vLLM loader.
        source = SimpleNamespace(total_frames_num=len(frames), original_fps=source_fps,
                                 duration=metadata['duration'])
        target = SimpleNamespace(num_frames=-1, fps=fps)
        offsets = VideoBackend.compute_frames_index_to_sample(source, target)
        policy = 'main_vllm_opencv_uniform'
    else:
        # Same native processor sampling and frame-count bounds as main Qwen/Cosmos.
        valid = {field.name for field in fields(VideoMetadata)}
        hf_metadata = VideoMetadata(**{k: v for k, v in metadata.items() if k in valid})
        offsets = processor.video_processor.sample_frames(hf_metadata, fps=fps).tolist()
        policy = 'main_hf_processor_sample_frames'
    indices = [source_indices[i] for i in offsets]
    metadata['frames_indices'] = indices
    sampled = frames[np.asarray(offsets)]
    audit = {'requested_fps': fps, 'source_fps': source_fps,
             'source_indices': indices, 'timestamps_seconds': [i / source_fps for i in indices],
             'sampled_frames': len(indices), 'sampling': policy}
    if family != 'gemma':
        audit.update(min_frames=processor.video_processor.min_frames,
                     max_frames=processor.video_processor.max_frames)
    return (sampled, metadata), audit


def prepare_video(processor, target, args, *, messages=None, continuation=False, sample_cache=None):
    """Sample raw decoded frames once and reuse them for assistant continuation."""
    from .sampling import SAMPLING
    cache = sample_cache if sample_cache is not None else {}
    if 'positive' not in cache:
        media = load_frames(target['video_path'], 'cosmos')
        cache['positive'] = sample_media(media, SAMPLING[args.model_family].positive_fps,
                                         family=args.model_family, processor=processor)
    positive, audit = cache['positive']
    full = prepare_inputs(processor, messages if messages is not None else target['messages'],
                          family=args.model_family, media=positive, continuation=continuation,
                          thinking=not args.disable_thinking,
                          video_kwargs={'do_sample_frames': False, 'return_metadata': True})
    audit = copy.deepcopy(audit)
    annotate_grid(audit, full, processor)
    return full, None, {'positive': audit}


def annotate_grid(audit, inputs, processor):
    if 'video_grid_thw' in inputs:
        audit['video_grid_thw'] = inputs['video_grid_thw'].tolist()
        audit['temporal_patch_size'] = int(processor.video_processor.temporal_patch_size)
