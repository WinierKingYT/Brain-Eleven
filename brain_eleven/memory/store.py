"""Stable package boundary for the canonical memory store.

The implementation remains in ``scripts/memory_store.py`` during the
incremental repository consolidation. This adapter re-exports the exact
legacy objects so callers can migrate without creating a second authority.
"""

from __future__ import annotations

import sys
from pathlib import Path


_ROOT = Path(__file__).resolve().parents[2]
_SCRIPTS = _ROOT / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from memory_store import (  # noqa: E402
    CANONICAL_SCHEMA_VERSION,
    MemoryStore,
    MemoryStoreConflict,
    MemoryStoreCorrupt,
    MemoryStoreError,
    no_change,
)

__all__ = [
    "CANONICAL_SCHEMA_VERSION",
    "MemoryStore",
    "MemoryStoreConflict",
    "MemoryStoreCorrupt",
    "MemoryStoreError",
    "no_change",
]
