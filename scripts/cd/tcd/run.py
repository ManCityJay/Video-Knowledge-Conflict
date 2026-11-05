#!/usr/bin/env python3
"""Run TCD independently with the shared experiment protocol."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from cd.contrastive_common.cli import main

if __name__ == '__main__':
    raise SystemExit(main(method='tcd'))
