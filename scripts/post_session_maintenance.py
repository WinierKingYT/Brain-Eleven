#!/usr/bin/env python3
"""Compatibility/direct-execution adapter for runtime maintenance."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from types import ModuleType


_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    # Historical direct execution starts with ``scripts/`` on sys.path.
    sys.path.insert(0, str(_ROOT))


# Keep the migration contract explicit: operational callers use packaged
# extraction, support, and memory surfaces rather than legacy script modules.
from brain_eleven.support import (  # noqa: F401,E402
    AnomalyDetector,
    MemorySummarizer,
    setup_logging,
)
from brain_eleven.extraction import EntityExtractor  # noqa: F401,E402
from brain_eleven.memory import MemoryStore, MemoryStoreError  # noqa: F401,E402


def _load_canonical(name: str, path: Path) -> ModuleType:
    """Load and cache the package implementation for the legacy entrypoint."""

    existing = sys.modules.get(name)
    if existing is not None:
        return existing
    if not path.is_file():
        raise ImportError(f"Cannot load canonical module: {path}")
    module = importlib.import_module(name)
    sys.modules.setdefault(name, module)
    return module


_maintenance = _load_canonical(
    "brain_eleven.runtime.maintenance",
    _ROOT / "brain_eleven" / "runtime" / "maintenance.py",
)

SURFACE_THRESHOLD = _maintenance.SURFACE_THRESHOLD
_run_step = _maintenance._run_step
run_maintenance = _maintenance.run_maintenance
save_report = _maintenance.save_report
summarize_for_shell = _maintenance.summarize_for_shell
main = _maintenance.main
logger = _maintenance.logger

__all__ = [
    "SURFACE_THRESHOLD",
    "_run_step",
    "run_maintenance",
    "save_report",
    "summarize_for_shell",
    "main",
    "logger",
]


# Existing tests and third-party callers historically import the bare module
# name. Point that name at the canonical module so monkeypatching dependencies
# retains the old behavior while the adapter remains implementation-free.
if __name__ == "scripts.post_session_maintenance":
    sys.modules.setdefault("post_session_maintenance", _maintenance)


if __name__ == "__main__":
    raise SystemExit(main())
