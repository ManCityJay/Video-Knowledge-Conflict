"""Main-pipeline prompts and OpenCV / HF preprocessing, without frame caps."""
from __future__ import annotations

import copy
from pathlib import Path

from vconflict_pipeline.qa import _cosmos_prompt, _video_question_prompt


def template_kwargs(family, thinking=True):
    if family == 'qwen':
        return {'enable_thinking': thinking, **({'reasoning_effort': 'xhigh'} if thinking else {})}
    return {'enable_thinking': thinking} if family == 'gemma' else {}


def build_messages(question, *, family, video=None, based=False, work_title=None, thinking=True):
    prompt = _video_question_prompt(question, work_title=work_title,
                                    work_title_prefix=work_title is not None, based=based)
    if family == "cosmos":
        prompt = _cosmos_prompt(prompt, 'default' if thinking else None)
    content = ([{"type": "video", "path": str(video)}] if video is not None else [])
    content.append({"type": "text", "text": prompt})
    result = [] if family == "qwen" else [
        {"role": "system", "content": "You are a helpful assistant."}]
    return result + [{"role": "user", "content": content}]


def load_frames(path, family):
    # Exactly the loader used by the main vLLM endpoint, in this same environment.
    from vllm.multimodal.video import VideoBackend
    frames, metadata = VideoBackend.load_bytes(
        Path(path).read_bytes(), backend="opencv", num_frames=-1,
        fps=1 if family == "gemma" else -1)
    if not len(frames) or not metadata.get("fps") or metadata["fps"] <= 0:
        raise ValueError("Video must contain decodable frames and a positive FPS")
    return frames, metadata


def gemma_inputs(processor, rendered, frames, metadata):
    """vLLM processes video frames as PIL images at max_soft_tokens=70.

    HF's native Gemma video processor uses a different normalization path, so
    explicitly use its image processor and map to the HF video tower inputs.
    """
    import torch
    from PIL import Image
    images = [Image.fromarray(frame) for frame in frames]
    image_inputs = processor.image_processor(images=images, max_soft_tokens=70,
                                              return_tensors="pt")
    counts = [int(n) for n in image_inputs["num_soft_tokens_per_image"]]
    if len(counts) != len(frames) or any(n > 70 for n in counts):
        raise ValueError("Unexpected Gemma visual token allocation")
    timestamps = [i / metadata["fps"] for i in metadata["frames_indices"]]
    replacement = " ".join(
        f"{int(t // 60):02d}:{int(t % 60):02d} "
        f"{processor.boi_token}{processor.video_token * n}{processor.eoi_token}"
        for t, n in zip(timestamps, counts))
    if rendered.count(processor.video_token) != 1:
        raise ValueError("Expected one Gemma video placeholder")
    rendered = rendered.replace(processor.video_token, replacement)
    result = dict(processor.tokenizer(rendered, add_special_tokens=False, return_tensors="pt"))
    result["mm_token_type_ids"] = torch.tensor(
        processor.create_mm_token_type_ids(result["input_ids"].tolist()), dtype=torch.long)
    result["pixel_values_videos"] = image_inputs["pixel_values"].unsqueeze(0)
    positions = image_inputs.get("image_position_ids", image_inputs.get("pixel_position_ids"))
    result["video_position_ids"] = positions.unsqueeze(0)
    return result


def prepare_inputs(processor, messages, *, family, media=None, continuation=False, thinking=True):
    """Render each branch's prompt with shared template settings and assistant history."""
    kwargs = template_kwargs(family, thinking)
    rendered = processor.apply_chat_template(
        messages, tokenize=False, add_generation_prompt=not continuation,
        continue_final_message=continuation, **kwargs)
    has_video = any(isinstance(m["content"], list) and
                    any(p.get("type") == "video" for p in m["content"]) for m in messages)
    if not has_video:
        result = dict(processor(text=[rendered], add_special_tokens=False, return_tensors="pt"))
    else:
        frames, metadata = media
        metadata = copy.deepcopy(metadata)
        if family == "gemma":
            result = gemma_inputs(processor, rendered, frames, metadata)
        else:
            from dataclasses import fields
            from transformers.video_utils import VideoMetadata
            metadata = {k: v for k, v in metadata.items()
                        if k in {f.name for f in fields(VideoMetadata)}}
            metadata = VideoMetadata(**metadata)
            result = dict(processor(
                text=[rendered], videos=[frames], video_metadata=[metadata],
                add_special_tokens=False, return_tensors="pt",
                videos_kwargs={"fps": 4 if family == "cosmos" else 1,
                               "do_sample_frames": True, "return_metadata": True}))
        result.pop("video_metadata", None)
    return result
