"""Stable package boundary for read-only current-state resolution.

The Phase 16 resolver remains backed by ``scripts/state_resolver.py`` during
the strangler migration.  Re-exporting its exact objects keeps all callers on
one resolver implementation while preserving fail-closed state semantics.
"""

from __future__ import annotations

from brain_eleven._legacy import load_legacy_module


_legacy = load_legacy_module("state_resolver", "state_resolver.py")

PROJECT_ARCHIVED = _legacy.PROJECT_ARCHIVED
PROJECT_UNKNOWN = _legacy.PROJECT_UNKNOWN
STATE_AVAILABLE = _legacy.STATE_AVAILABLE
STATE_CORRUPT = _legacy.STATE_CORRUPT
STATE_NOT_FOUND = _legacy.STATE_NOT_FOUND
STATE_UNAVAILABLE = _legacy.STATE_UNAVAILABLE
CurrentProjectState = _legacy.CurrentProjectState
StateResolver = _legacy.StateResolver

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
