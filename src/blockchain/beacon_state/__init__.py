"""Beacon-state handling.

Put the generated consensus-specs types (``consensus-spec/eth_consensus_specs``) on sys.path
here, at package import time, so ``specs.py`` and everything under it can import them with plain
imports and the service works the same under pytest, in Docker and in a local
``python src/main.py`` run.
"""

import sys
from pathlib import Path

_CONSENSUS_SPEC_DIR = Path(__file__).resolve().parents[3] / 'consensus-spec'
if _CONSENSUS_SPEC_DIR.is_dir() and str(_CONSENSUS_SPEC_DIR) not in sys.path:
    sys.path.insert(0, str(_CONSENSUS_SPEC_DIR))
