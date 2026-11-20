"""Pytest config runner: paket `mufakat_runner` diambil dari folder runner ini."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
