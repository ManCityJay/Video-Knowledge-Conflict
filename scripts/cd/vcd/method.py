"""Prepare one VCD branch from its messages and original decoded media."""
from cd.contrastive_common.video import prepare_inputs


def prepare(processor, messages, args, *, media=None, continuation=False):
    return prepare_inputs(processor, messages, family=args.model_family, media=media,
                          continuation=continuation, thinking=not args.disable_thinking)
