"""SEASON input preparation, intervention branches and attention-weighted scores."""
from contextlib import AbstractContextManager, nullcontext

import torch

from cd.contrastive_common.adapters import Branch
from cd.contrastive_common.batching import collate
from cd.contrastive_common.core import combine_logits
from cd.contrastive_common.media import prepare_video
from . import interventions as season


def prepare(processor, target, args, *, messages=None, continuation=False, sample_cache=None):
    return prepare_video(processor, target, args, messages=messages,
                         continuation=continuation, sample_cache=sample_cache)


class Decoder(AbstractContextManager):
    def __init__(self, model, processor, states, positive, negative, args, dtype):
        self.model, self.processor, self.states = model, processor, states
        self.positive, self.args, self.dtype = positive, args, dtype
        self.capture = season.DecoderAttentionCapture(model) if args.alpha else nullcontext()
        self.diagnostics = None
        self.extra = [{} for _ in states]

    def __enter__(self):
        self.cap = self.capture.__enter__()
        try:
            self.left = Branch(self.model, self.positive, self.args.device, self.dtype)
            self.right = self.temporal = None
            if not self.args.alpha:
                self.lo = self.left.logits()
                return self
            self.geometry = season.layout(self.model, self.positive, self.processor)
            # Draw noise per sample: batch composition and order cannot change it.
            spatial = collate([season.spatial_noise(s['positive'], noise_step=self.args.noise_step,
                                                   seed=self.args.noise_seed) for s in self.states],
                              self.processor.tokenizer)
            self.right = Branch(self.model, spatial, self.args.device, self.dtype)
            self.temporal = Branch(self.model, self.positive, self.args.device, self.dtype)
            anchors = []
            with season.VisionHomogenization(self.model, anchors, self.geometry, capture=True):
                self.lo = self.left.logits()
            self.ao = self.cap.stacked().clone()
            if len(anchors) != len(season.vision_blocks(self.model)):
                raise ValueError('Incomplete clean SEASON anchors')
            with season.VisionHomogenization(self.model, anchors, self.geometry, beta=self.args.season_beta):
                self.lt = self.temporal.logits()
            self.at = self.cap.stacked().clone()
            self.ls = self.right.logits()
            self.a_s = self.cap.stacked().clone()
            self.diagnostics = self.lo.new_zeros((len(self.states), 5), dtype=torch.float32)
            self.extra = [{'selected_attention_layers': list(self.cap.selected),
                           'layer_policy': 'last_four_full_attention_layers',
                           'temporal_units': self.geometry[1], 'vision_spatial_tokens': self.geometry[2],
                           'decoder_spatial_tokens': self.geometry[3]} for _ in self.states]
            return self
        except BaseException:
            self.capture.__exit__(None, None, None)
            raise

    @property
    def sequence(self):
        return self.left.sequence

    def scores(self, suppressed, active):
        if not self.args.alpha:
            return combine_logits(self.lo, None, alpha=0., beta=self.args.beta, suppress_tokens=suppressed)
        scores, weights = season.season_scores((self.lo, self.ls, self.lt),
                                               (self.ao, self.a_s, self.at), self.geometry, self.args.alpha)
        self.diagnostics += weights * weights.new_tensor(active)[:, None]
        if suppressed:
            scores[:, suppressed] = -torch.inf
        return scores

    def advance(self, token):
        self.lo = self.left.logits(token)
        if self.temporal is not None:
            self.ao = self.cap.stacked().clone()
            self.ls = self.right.logits(token)
            self.a_s = self.cap.stacked().clone()
            self.lt = self.temporal.logits(token)
            self.at = self.cap.stacked().clone()
            caches = [branch.kwargs.get('past_key_values') for branch in (self.left, self.right, self.temporal)]
            if len({id(cache) for cache in caches}) != 3:
                raise RuntimeError('SEASON branches unexpectedly share a KV cache')

    def metadata(self, ids):
        if self.diagnostics is not None:
            for index, values in enumerate(self.diagnostics.tolist()):
                self.extra[index]['mean_diagnostics'] = dict(zip(
                    ('spatial_weight', 'temporal_weight', 'divergence_spatial', 'divergence_temporal'),
                    [v / max(1, len(ids[index])) for v in values[:4]]))
                self.extra[index]['fallback_tokens'] = int(values[4])
        return self.extra

    def __exit__(self, *exc):
        return self.capture.__exit__(*exc)
