#!/usr/bin/env python3
"""Independent VCD entry point using the main experiment's dataset protocol."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cd.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
