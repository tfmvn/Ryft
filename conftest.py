"""Pytest config — make the repo root importable so ``import ryft`` resolves
from ``tests/`` without a pip install."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
