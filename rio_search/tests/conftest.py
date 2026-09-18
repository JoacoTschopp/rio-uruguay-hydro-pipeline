"""Pone la raíz del repo en sys.path para que `rio_search` sea importable."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
