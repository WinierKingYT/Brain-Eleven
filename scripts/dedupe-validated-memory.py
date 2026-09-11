#!/usr/bin/env python3
"""Compatibility/direct-execution adapter for lifecycle deduplication."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from types import ModuleType


_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def _load_canonical(name: str) -> ModuleType:
    """Load and cache the package implementation once."""

    existing = sys.modules.get(name)
    if existing is not None:
        return existing
    module = importlib.import_module(name)
    sys.modules.setdefault(name, module)
    return module


_dedupe = _load_canonical("brain_eleven.lifecycle.dedupe")

SUPERSESSION_NOTE = _dedupe.SUPERSESSION_NOTE
MemoryLifecycleManager = _dedupe.MemoryLifecycleManager
plan_dedupe = _dedupe.plan_dedupe
main = _dedupe.main

__all__ = ["SUPERSESSION_NOTE", "MemoryLifecycleManager", "plan_dedupe", "main"]

# Preserve the historical import name used by direct loaders and old tools.
if __name__ in {"scripts.dedupe_validated_memory", "dedupe_validated_memory"}:
    sys.modules.setdefault("dedupe_validated_memory", _dedupe)


if __name__ == "__main__":
    raise SystemExit(main())
