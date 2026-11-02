"""Local model loading and isolated generation state for CD branches."""
from __future__ import annotations


def load_runtime(family: str, path: str, device: str, dtype_name: str):
    import torch
    import transformers
    from transformers import AutoConfig, AutoProcessor

    if transformers.__version__ != "5.18.0":
        raise ValueError("VCD protocol requires transformers==5.18.0")

    dtype = getattr(torch, dtype_name)
    torch.manual_seed(0)
    config = AutoConfig.from_pretrained(path, local_files_only=True, trust_remote_code=False)
    expected = {"cosmos": "cosmos3_omni", "qwen": "qwen3_5", "gemma": "gemma4"}[family]
    if config.model_type != expected:
        raise ValueError(f"{family} requires model_type={expected}, got {config.model_type}")
    processor = AutoProcessor.from_pretrained(path, local_files_only=True, trust_remote_code=False)
    if family == "cosmos":
        from transformers import Cosmos3OmniForConditionalGeneration
        model_class = Cosmos3OmniForConditionalGeneration
    else:
        from transformers import AutoModelForImageTextToText
        model_class = AutoModelForImageTextToText
    model = model_class.from_pretrained(
        path, local_files_only=True, trust_remote_code=False, dtype=dtype,
        attn_implementation="sdpa").to(device).eval()
    return model, processor, dtype


def move_inputs(inputs, device, dtype):
    import torch

    def move(value):
        if isinstance(value, torch.Tensor):
            return value.to(device=device, dtype=dtype if value.is_floating_point() else value.dtype)
        if isinstance(value, dict):
            return {k: move(v) for k, v in value.items()}
        if isinstance(value, (tuple, list)):
            return type(value)(move(v) for v in value)
        return value

    return {k: move(v) for k, v in inputs.items()}


def eos_ids(model, processor):
    value = model.generation_config.eos_token_id
    if value is None:
        value = processor.tokenizer.eos_token_id
    if value is None:
        raise ValueError("no EOS token configured")
    ids = {int(value)} if isinstance(value, int) else set(map(int, value))
    if not ids or min(ids) < 0:
        raise ValueError("invalid EOS token IDs")
    return ids


class Branch:
    """Each branch owns KV cache, generation kwargs, positions and RoPE deltas."""

    def __init__(self, model, inputs, device, dtype):
        self.model = model
        self.inputs = move_inputs(inputs, device, dtype)
        self.sequence = self.inputs["input_ids"].clone()
        self.kwargs = {k: v for k, v in self.inputs.items() if k != "input_ids"}
        self.kwargs["use_cache"] = True
        self.owner = getattr(model, "model", model)
        self.has_rope = hasattr(self.owner, "rope_deltas")
        old = getattr(self.owner, "rope_deltas", None)
        try:
            if self.has_rope:
                self.owner.rope_deltas = None
            self.kwargs["position_ids"] = model._prepare_position_ids_for_generation(self.sequence, self.kwargs)
            delta = getattr(self.owner, "rope_deltas", None)
            self.rope_deltas = None if delta is None else delta.clone()
        finally:
            if self.has_rope:
                self.owner.rope_deltas = old
        self.first = True

    def logits(self, token=None):
        import torch

        if token is not None:
            if self.first:
                raise ValueError("cannot advance before prefill")
            self.sequence = torch.cat([self.sequence, token.reshape(1, 1)], dim=-1)
        elif not self.first:
            raise ValueError("need a token to advance cached branch")
        old = getattr(self.owner, "rope_deltas", None)
        try:
            if self.has_rope:
                self.owner.rope_deltas = self.rope_deltas
            step = self.model.prepare_inputs_for_generation(
                self.sequence, **self.kwargs, is_first_iteration=self.first,
                next_sequence_length=None if self.first else 1)
            step.update(return_dict=True, logits_to_keep=1)
            output = self.model(**step)
            self.kwargs = self.model._update_model_kwargs_for_generation(
                output, self.kwargs, is_encoder_decoder=False)
            delta = getattr(self.owner, "rope_deltas", None)
            self.rope_deltas = None if delta is None else delta.clone()
            self.first = False
            return output.logits[:, -1, :]
        finally:
            if self.has_rope:
                self.owner.rope_deltas = old
