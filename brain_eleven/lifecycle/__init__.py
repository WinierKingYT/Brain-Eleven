"""Canonical lifecycle package surface for the strangler migration.

The implementation remains in the legacy hyphenated CLI module while callers
move behind a stable import path.  Re-exporting the exact implementation
object preserves lifecycle behavior and avoids a second mutation authority.
"""

from __future__ import annotations

from brain_eleven._legacy import load_legacy_module


_legacy = load_legacy_module("memory_lifecycle", "memory-lifecycle.py")

MemoryLifecycleManager = _legacy.MemoryLifecycleManager

__all__ = ["MemoryLifecycleManager"]
