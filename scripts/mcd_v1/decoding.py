"""MCD v1: log p(video) - lambda * log p(text), with shared output history.

The video branch uses Transformers' normal generate/cache machinery. The text
branch recomputes its (short) full prefix at each step, deliberately without a
KV cache in v1. This avoids coordinating two caches while retaining the exact
conditional distribution required by the method. No vision work is repeated in
the negative branch. Only single-sample greedy generation is supported.
"""

from __future__ import annotations

import math

import torch


def validate_parameters(weight: float, beta: float) -> None:
    if not math.isfinite(weight) or weight < 0:
        raise ValueError("lambda must be finite and >= 0")
    if not math.isfinite(beta) or not 0 <= beta <= 1:
        raise ValueError("beta must be between 0 and 1 (0 disables the cutoff)")


def contrastive_scores(video_logits, text_logits, *, weight=0.5, beta=0.1):
    """Combine raw next-token logits in FP32; beta=0 means no cutoff.

    lambda=0 returns the original logits exactly, including their tie ordering.
    For positive lambda, the cutoff always keeps the video argmax available.
    """
    validate_parameters(weight, beta)
    if not torch.isfinite(video_logits).all():
        raise ValueError("Non-finite video logits")
    if weight == 0:
        return video_logits
    if text_logits is None or text_logits.shape != video_logits.shape:
        raise ValueError("Both branches must have the same batch/vocabulary shape")
    if not torch.isfinite(text_logits).all():
        raise ValueError("Non-finite text logits")
    log_video = torch.log_softmax(video_logits.float(), dim=-1)
    log_text = torch.log_softmax(text_logits.float(), dim=-1)
    scores = log_video - weight * log_text
    if not torch.isfinite(scores).all():
        raise ValueError("Non-finite contrastive scores")
    if beta > 0:
        allowed = log_video >= log_video.amax(dim=-1, keepdim=True) + math.log(beta)
        scores = scores.masked_fill(~allowed, -torch.inf)
    return scores


class TextPriorContrastiveProcessor:
    """A callable for Hugging Face's logits_processor list.

    The expert input_ids include its video prompt and the CURRENT generated
    suffix. Appending that suffix to the text prompt is teacher forcing, not
    independently generating a text answer. Cosmos keeps RoPE state on the
    shared model object; temporarily clear it for the text pass and restore it
    even if that pass raises an exception.
    """

    def __init__(self, model, text_inputs, video_prompt_length, *, weight=0.5, beta=0.1):
        validate_parameters(weight, beta)
        if video_prompt_length <= 0:
            raise ValueError("The video prompt must not be empty")
        if text_inputs["input_ids"].ndim != 2 or text_inputs["input_ids"].shape[0] != 1:
            raise ValueError("MCD v1 supports exactly one sample at a time")
        allowed_keys = {"input_ids", "attention_mask", "mm_token_type_ids"}
        if set(text_inputs) - allowed_keys:
            raise ValueError(f"Unexpected text-only inputs: {set(text_inputs) - allowed_keys}")
        if not hasattr(model.model, "rope_deltas"):
            raise ValueError("Expected Cosmos3Omni model with model.rope_deltas")
        self.model = model
        self.text_inputs = text_inputs
        self.video_prompt_length = video_prompt_length
        self.weight = weight
        self.beta = beta

    @torch.inference_mode()
    def __call__(self, input_ids, scores):
        if input_ids.shape[0] != 1 or input_ids.shape[1] < self.video_prompt_length:
            raise ValueError("MCD v1 requires an unmodified single-sample video prefix")
        if self.weight == 0:
            return contrastive_scores(scores, None, weight=0, beta=self.beta)

        history = input_ids[:, self.video_prompt_length:]
        prefix = self.text_inputs["input_ids"]
        history = history.to(prefix.device)
        text_ids = torch.cat((prefix, history), dim=-1)
        prefix_mask = self.text_inputs.get("attention_mask", torch.ones_like(prefix))
        attention_mask = torch.cat((prefix_mask, torch.ones_like(history)), dim=-1)
        text_kwargs = {"input_ids": text_ids, "attention_mask": attention_mask}
        if "mm_token_type_ids" in self.text_inputs:
            text_kwargs["mm_token_type_ids"] = torch.cat(
                (self.text_inputs["mm_token_type_ids"], torch.zeros_like(history)), dim=-1
            )

        video_rope = self.model.model.rope_deltas
        try:
            self.model.model.rope_deltas = None
            output = self.model(**text_kwargs, use_cache=False, logits_to_keep=1, return_dict=True)
            text_logits = output.logits[:, -1, :].to(scores.device)
        finally:
            self.model.model.rope_deltas = video_rope
        return contrastive_scores(scores, text_logits, weight=self.weight, beta=self.beta)
