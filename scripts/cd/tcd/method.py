"""Dense/sparse video sampling and isolated TCD branch state."""
import copy
from contextlib import AbstractContextManager

from cd.contrastive_common.adapters import Branch
from cd.contrastive_common.core import combine_logits
from cd.contrastive_common.media import annotate_grid, prepare_video, sample_media
from cd.contrastive_common.sampling import SAMPLING
from cd.contrastive_common.video import load_frames, prepare_inputs


def prepare(processor, target, args, *, messages=None, continuation=False, sample_cache=None):
    cache = sample_cache if sample_cache is not None else {}
    if 'positive' not in cache:
        media = load_frames(target['video_path'], 'cosmos')
        rates = SAMPLING[args.model_family]
        cache['positive'] = sample_media(media, rates.positive_fps,
                                         family=args.model_family, processor=processor)
        if args.alpha:
            cache['negative'] = sample_media(media, rates.negative_fps,
                                             family=args.model_family, processor=processor)
    full, _, audit = prepare_video(processor, target, args, messages=messages,
                                    continuation=continuation, sample_cache=cache)
    negative = None
    if args.alpha:
        sparse, neg_audit = cache['negative']
        options = {'do_sample_frames': False, 'return_metadata': True}
        if args.model_family != 'gemma':
            import torch
            from torchvision.transforms.v2 import functional as F
            from torchvision.transforms import InterpolationMode
            grid = full['video_grid_thw'][0]
            patch = int(processor.video_processor.patch_size)
            hw = [int(grid[1]) * patch, int(grid[2]) * patch]
            frames, metadata = sparse
            pixels = torch.from_numpy(frames).permute(0, 3, 1, 2)
            pixels = F.resize(pixels, hw, interpolation=InterpolationMode.BICUBIC, antialias=True)
            sparse = (pixels.permute(0, 2, 3, 1).numpy(), metadata)
            options['do_resize'] = False
            audit['shared_resize_hw'] = hw
        negative = prepare_inputs(
            processor, messages if messages is not None else target['messages'],
            family=args.model_family, media=sparse, continuation=continuation,
            thinking=not args.disable_thinking, video_kwargs=options)
        if args.model_family != 'gemma' and not (full['video_grid_thw'][:, 1:] ==
                                                 negative['video_grid_thw'][:, 1:]).all():
            raise ValueError('TCD positive and negative spatial grids differ')
        if args.model_family == 'gemma' and (
                full['pixel_values_videos'].shape[2:] != negative['pixel_values_videos'].shape[2:]
                or not (full['video_position_ids'][:, :1] == negative['video_position_ids'][:, :1]).all()):
            raise ValueError('TCD positive and negative spatial resolutions differ')
        audit['negative'] = copy.deepcopy(neg_audit)
        annotate_grid(audit['negative'], negative, processor)
    return full, negative, audit


class Decoder(AbstractContextManager):
    def __init__(self, model, processor, states, positive, negative, args, dtype):
        self.args = args
        self.left = Branch(model, positive, args.device, dtype)
        self.right = Branch(model, negative, args.device, dtype) if args.alpha else None
        self.lp, self.ln = self.left.logits(), self.right.logits() if self.right else None

    @property
    def sequence(self):
        return self.left.sequence

    def scores(self, suppressed, active):
        return combine_logits(self.lp, self.ln, alpha=self.args.alpha, beta=self.args.beta,
                              suppress_tokens=suppressed)

    def advance(self, token):
        self.lp = self.left.logits(token)
        if self.right:
            self.ln = self.right.logits(token)
            if self.left.kwargs.get('past_key_values') is self.right.kwargs.get('past_key_values'):
                raise RuntimeError('TCD branches unexpectedly share a KV cache')

    def metadata(self, ids):
        return [{} for _ in ids]

    def __exit__(self, *exc):
        return False
