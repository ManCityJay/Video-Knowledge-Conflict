"""SEASON visual interventions and last-query attention for real tensor batches.

Ported from scripts/mcd/multimodel/season.py in Video-Knowledge-Conflict.
Spatial noise and temporal anchors retain that implementation's math; each
sample owns its anchors and attention weights, including when batch size > 1.
"""
from __future__ import annotations

import copy
from contextlib import AbstractContextManager

import torch
from transformers.modeling_utils import ALL_ATTENTION_FUNCTIONS


def vision_blocks(model):
    root = model.model
    return root.vision_tower.encoder.layers if model.config.model_type == 'gemma4' else root.visual.blocks


def selected_layers(model):
    config = model.config.get_text_config()
    layers = model.model.language_model.layers
    types = getattr(config, 'layer_types', ['full_attention'] * len(layers))
    selected = [i for i, kind in enumerate(types) if kind == 'full_attention']
    if not selected:
        raise ValueError('SEASON requires full/global decoder attention')
    return tuple(selected[-4:])


def layout(model, inputs, processor):
    batch = inputs['input_ids'].shape[0]
    token_id = model.config.video_token_id
    if model.config.model_type == 'gemma4':
        pixels = inputs['pixel_values_videos']
        if pixels.ndim != 4 or pixels.shape[0] != batch:
            raise ValueError('Expected Gemma [batch, frames, patches, patch_dim]')
        t, spatial = map(int, pixels.shape[1:3])
        positions = inputs['video_position_ids']
        if positions.shape[:3] != pixels.shape[:3]:
            raise ValueError('Gemma pixel positions disagree')
        if not torch.equal(positions, positions[:, :1].expand_as(positions)):
            raise ValueError('Temporal anchors require matching per-frame patch positions')
        counts = (inputs['input_ids'] == token_id).sum(-1)
        if not (counts == counts[0]).all() or int(counts[0]) % t:
            raise ValueError('Batch has incompatible visual token counts')
        decoder_spatial = int(counts[0]) // t
    else:
        grid = inputs['video_grid_thw']
        if grid.shape != (batch, 3) or not torch.equal(grid, grid[:1].expand_as(grid)):
            raise ValueError('SEASON batch requires equal video grids')
        t, h, w = map(int, grid[0].tolist())
        merge = int(processor.video_processor.merge_size)
        if h % merge or w % merge:
            raise ValueError('Invalid spatial grid')
        spatial, decoder_spatial = h * w, h * w // (merge * merge)
    patches = [torch.nonzero(row == token_id, as_tuple=False).flatten()
               for row in inputs['input_ids']]
    if decoder_spatial < 1 or any(p.numel() != t * decoder_spatial for p in patches):
        raise ValueError('Visual token count disagrees with grid')
    return batch, t, spatial, decoder_spatial, torch.stack(patches)


def spatial_noise(inputs, *, noise_step, seed):
    pixels = inputs['pixel_values_videos']
    steps = torch.linspace(-6., 6., 1000, dtype=torch.float64)
    schedule = 1e-5 + (.005 - 1e-5) * torch.sigmoid(steps)
    alpha = torch.cumprod(1 - schedule, 0)[noise_step - 1] if noise_step else torch.tensor(1.)
    generator = torch.Generator(device=pixels.device).manual_seed(seed)
    noise = torch.randn(pixels.shape, generator=generator, device=pixels.device, dtype=pixels.dtype)
    result = dict(inputs)
    result['pixel_values_videos'] = alpha.sqrt().to(pixels.dtype) * pixels + (1 - alpha).sqrt().to(pixels.dtype) * noise
    return result


class VisionHomogenization(AbstractContextManager):
    def __init__(self, model, anchors, geometry, *, beta=0., capture=False):
        self.blocks, self.anchors = vision_blocks(model), anchors
        self.batch, self.t, self.s = geometry[:3]
        self.beta, self.capture, self.handles = beta, capture, []

    def __enter__(self):
        try:
            for index, block in enumerate(self.blocks):
                def hook(module, args, value, index=index):
                    x = value[0] if isinstance(value, (tuple, list)) else value
                    flat = x.reshape(-1, x.shape[-1])
                    if flat.shape[0] != self.batch * self.t * self.s:
                        raise ValueError('Vision batch geometry mismatch')
                    rows = flat.reshape(self.batch, self.t, self.s, -1)
                    if self.capture:
                        if len(self.anchors) != index:
                            raise ValueError('Vision blocks visited out of order')
                        self.anchors.append(rows.detach().mean(dim=1).clone())
                        return value
                    anchor = self.anchors[index].unsqueeze(1)
                    y = ((1 - self.beta) * rows + self.beta * anchor).reshape(x.shape)
                    if isinstance(value, tuple):
                        return (y, *value[1:])
                    if isinstance(value, list):
                        return [y, *value[1:]]
                    return y
                self.handles.append(block.register_forward_hook(hook))
        except BaseException:
            self.__exit__(None, None, None)
            raise
        return self

    def __exit__(self, *exc):
        for handle in reversed(self.handles):
            handle.remove()
        self.handles.clear()
        return False


def _capture_backend(module, query, key, value, attention_mask, dropout=0., scaling=None, **kwargs):
    native = module._vkc_season_native
    scaling = module.head_dim**-.5 if scaling is None else scaling
    result = native(module, query, key, value, attention_mask, dropout=dropout, scaling=scaling, **kwargs)
    if query.shape[1] % key.shape[1]:
        raise ValueError('Invalid grouped-query attention geometry')
    batch, query_heads, _, dim = query.shape
    key_heads = key.shape[1]
    last_query = query[..., -1, :].reshape(batch, key_heads, query_heads // key_heads, dim)
    # Do not replicate the full KV tensor across grouped-query heads.
    scores = torch.matmul(last_query.float(), key.float().transpose(-1, -2))
    scores = scores.reshape(batch, query_heads, 1, key.shape[-2]) * scaling
    softcap = kwargs.get('softcap')
    if softcap is not None:
        scores = torch.tanh(scores / softcap) * softcap
    if attention_mask is not None:
        mask = attention_mask[..., -1:, :scores.shape[-1]]
        scores = scores.masked_fill(~mask, -torch.inf) if mask.dtype == torch.bool else scores + mask.float()
    rows = torch.softmax(scores, dim=-1).squeeze(-2).detach()
    if not torch.isfinite(rows).all():
        raise ValueError('Non-finite SEASON attention')
    module._vkc_season_sink[module] = rows
    return result


_CAPTURE_KEY = 'vkc_season_batched_last_row_v1'
ALL_ATTENTION_FUNCTIONS.register(_CAPTURE_KEY, _capture_backend)


class DecoderAttentionCapture(AbstractContextManager):
    def __init__(self, model):
        self.model, self.selected = model, selected_layers(model)
        self.saved, self.rows = [], {}

    def __enter__(self):
        from importlib import import_module
        architecture = {'cosmos3_omni': 'qwen3_vl', 'qwen3_5': 'qwen3_5', 'gemma4': 'gemma4'}[self.model.config.model_type]
        eager = import_module(f'transformers.models.{architecture}.modeling_{architecture}').eager_attention_forward
        try:
            for index in self.selected:
                module = self.model.model.language_model.layers[index].self_attn
                if hasattr(module, '_vkc_season_sink'):
                    raise RuntimeError('Nested SEASON attention capture')
                cfg = module.config
                native = ALL_ATTENTION_FUNCTIONS.get_interface(cfg._attn_implementation, eager)
                self.saved.append((module, cfg))
                module._vkc_season_native, module._vkc_season_sink = native, self.rows
                module.config = copy.copy(cfg)
                module.config._attn_implementation = _CAPTURE_KEY
        except BaseException:
            self.__exit__(None, None, None)
            raise
        return self

    def stacked(self):
        return torch.stack([self.rows[module] for module, _ in self.saved], dim=1)

    def __exit__(self, *exc):
        for module, cfg in reversed(self.saved):
            module.config = cfg
            for name in ('_vkc_season_native', '_vkc_season_sink'):
                if hasattr(module, name):
                    delattr(module, name)
        self.saved.clear()
        self.rows.clear()
        return False


def frame_attention(rows, patches, t, spatial):
    # [B, layers, heads, keys] -> [B, frames], exactly the old per-sample reduction.
    indices = patches.to(rows.device)[:, None, None, :].expand(*rows.shape[:3], -1)
    values = rows.gather(-1, indices).sum(dim=(1, 2)).reshape(rows.shape[0], t, spatial).sum(-1)
    return torch.softmax(values.float(), dim=-1)


def season_scores(logits, attentions, geometry, alpha):
    _, t, _, spatial, patches = geometry
    p, q, r = [frame_attention(a, patches, t, spatial) for a in attentions]
    def js(left, right):
        left = left / left.sum(-1, keepdim=True)
        right = right / right.sum(-1, keepdim=True)
        middle = (left + right) * .5
        return (.5 * (left * (left.clamp_min(1e-12).log() - middle.clamp_min(1e-12).log()) +
                      right * (right.clamp_min(1e-12).log() - middle.clamp_min(1e-12).log()))).sum(-1).clamp_min(0)
    ds, dt = js(p, q), js(p, r)
    total = ds + dt
    fallback = total <= 1e-12
    ws = torch.where(fallback, .5, ds / total.clamp_min(1e-12))
    wt = torch.where(fallback, .5, dt / total.clamp_min(1e-12))
    origin, spatial_logits, temporal_logits = [value.float() for value in logits]
    scores = (1 + alpha) * origin - alpha * (ws[:, None] * spatial_logits + wt[:, None] * temporal_logits)
    if not torch.isfinite(scores).all():
        raise ValueError('SEASON produced non-finite logits')
    return scores, torch.stack((ws, wt, ds, dt, fallback.float()), dim=-1)
