"""Stable package boundary for read-only current-state resolution.

The Phase 16 resolver remains backed by ``scripts/state_resolver.py`` during
the strangler migration.  Re-exporting its exact objects keeps all callers on
one resolver implementation while preserving fail-closed state semantics.
"""

from __future__ import annotations

import sys
from pathlib import Path


_ROOT = Path(__file__).resolve().parents[2]
_SCRIPTS = _ROOT / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from state_resolver import (  # noqa: E402
    PROJECT_ARCHIVED,
    PROJECT_UNKNOWN,
    STATE_AVAILABLE,
    STATE_CORRUPT,
    STATE_NOT_FOUND,
    STATE_UNAVAILABLE,
    CurrentProjectState,
    StateResolver,
)

__all__ = [
    "PROJECT_ARCHIVED",
    "PROJECT_UNKNOWN",
    "STATE_AVAILABLE",
    "STATE_CORRUPT",
    "STATE_NOT_FOUND",
    "STATE_UNAVAILABLE",
    "CurrentProjectState",
    "StateResolver",
]
