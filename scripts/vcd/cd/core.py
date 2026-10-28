"""FP32 contrastive logits and video plausibility filtering."""
from __future__ import annotations

import math


def validate_parameters(alpha: float, beta: float) -> None:
    if not math.isfinite(alpha) or alpha < 0:
        raise ValueError("alpha must be finite and >= 0")
    if not math.isfinite(beta) or not 0 < beta <= 1:
        raise ValueError("beta must be finite and in (0, 1]")


def combine_logits(video_logits, question_logits, *, alpha: float, beta: float):
    """Contrast raw logits, then keep plausible video candidates; alpha=0 bypasses both."""
    import torch

    validate_parameters(alpha, beta)
    if video_logits.ndim < 1 or video_logits.numel() == 0:
        raise ValueError("video logits must have a non-empty vocabulary")
    video_logits = video_logits.float()
    if not torch.isfinite(video_logits).all():
        raise ValueError("video logits contain non-finite values")
    if alpha == 0:
        return video_logits
    if question_logits is None or question_logits.shape != video_logits.shape:
        raise ValueError("video and question logits must have identical shapes")
    question_logits = question_logits.float()
    if not torch.isfinite(question_logits).all():
        raise ValueError("question logits contain non-finite values")
    scores = (1 + alpha) * video_logits - alpha * question_logits
    if not torch.isfinite(scores).all():
        raise ValueError("contrastive logits overflowed or contain non-finite values")
    cutoff = video_logits.amax(dim=-1, keepdim=True) + math.log(beta)
    scores = scores.masked_fill(video_logits < cutoff, -torch.inf)
    if not torch.isfinite(scores).any(dim=-1).all():
        raise ValueError("candidate mask removed every token")
    return scores

