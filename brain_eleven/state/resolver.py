"""Stable package boundary for read-only current-state resolution.

The Phase 16 resolver remains backed by ``scripts/state_resolver.py`` during
the strangler migration.  Re-exporting its exact objects keeps all callers on
one resolver implementation while preserving fail-closed state semantics.
"""

from __future__ import annotations

from scripts.state_resolver import (
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
