"""Load the selected TCD/SEASON batch method after GPU isolation and preflight."""
from importlib import import_module

MODULES = {'tcd': 'cd.tcd.method', 'season': 'cd.season.method'}


def get_method(method):
    if method not in MODULES:
        raise ValueError('Tensor batch execution supports TCD/SEASON only; VCD uses its serial runtime')
    return import_module(MODULES[method])
