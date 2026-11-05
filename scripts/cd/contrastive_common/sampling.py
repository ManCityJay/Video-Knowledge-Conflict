"""Model sampling rates shared by preprocessing, previews and QA fingerprints."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Sampling:
    positive_fps: float
    negative_fps: float


SAMPLING = {
    'qwen': Sampling(1.0, .5),
    'gemma': Sampling(1.0, .5),
    'cosmos': Sampling(4.0, 1.0),
}


def sampling_config(family, method):
    rates = SAMPLING[family]
    config = {'positive_fps': rates.positive_fps}
    if method == 'tcd':
        config['negative_fps'] = rates.negative_fps
    return config
