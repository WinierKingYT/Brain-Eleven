"""Canonical lifecycle package surface for the strangler migration.

The implementation remains in the legacy hyphenated CLI module while callers
move behind a stable import path.  Re-exporting the exact implementation
object preserves lifecycle behavior and avoids a second mutation authority.
"""

from __future__ import annotations

from .manager import MemoryLifecycleManager

from .dedupe import SUPERSESSION_NOTE, main as dedupe_main, plan_dedupe

__all__ = [
    "MemoryLifecycleManager",
    "SUPERSESSION_NOTE",
    "plan_dedupe",
    "dedupe_main",
]
