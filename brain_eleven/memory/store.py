"""Stable package boundary for the canonical memory store.

The implementation remains in ``scripts/memory_store.py`` during the
incremental repository consolidation. This adapter re-exports the exact
legacy objects so callers can migrate without creating a second authority.
"""

from __future__ import annotations

from scripts.memory_store import (
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
