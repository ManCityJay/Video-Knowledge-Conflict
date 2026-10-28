"""Resolve local model directories without downloads or weight inspection."""
from __future__ import annotations

import os
from pathlib import Path

from vconflict_pipeline.settings import COSMOS_QA_MODEL, GEMMA_QA_MODEL, QWEN38_QA_MODEL

MODELS = {'cosmos': COSMOS_QA_MODEL, 'gemma': GEMMA_QA_MODEL, 'qwen': QWEN38_QA_MODEL}
REVISIONS = {'cosmos': 'main', 'qwen': 'main',
             'gemma': '842da3794eaa0b77d5f08bae87a17459d91ff475'}


def resolve_model(family, explicit=None):
    if explicit is not None:
        path = explicit.expanduser().resolve(strict=True)
        if not (path / 'config.json').is_file():
            raise ValueError('--model must be a local model directory with config.json')
        return path
    cache = (Path(os.environ['HF_HUB_CACHE']) if os.environ.get('HF_HUB_CACHE') else
             Path(os.environ['HF_HOME']) / 'hub' if os.environ.get('HF_HOME') else
             Path('/cache/huggingface/hub')).expanduser().resolve()
    model, revision = MODELS[family], REVISIONS[family]
    detail = (f'Cannot resolve cached model {model} at revision {revision} in {cache}. '
              'Use --model /absolute/path/to/model to select a local directory; no download is attempted.')
    try:
        from huggingface_hub import try_to_load_from_cache
    except ImportError as exc:
        raise ValueError(detail + ' Offline resolution requires huggingface_hub in the active environment.') from exc
    cached = try_to_load_from_cache(model, 'config.json', revision=revision, cache_dir=cache)
    if not isinstance(cached, str):
        raise ValueError(detail)
    # Resolve the snapshot directory, not the config symlink into the blob store.
    return Path(cached).parent.resolve(strict=True)
