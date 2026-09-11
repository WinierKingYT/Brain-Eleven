#!/usr/bin/env python3
"""Compatibility adapter for the canonical memory provenance projection."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from types import ModuleType


_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    # Historical direct execution starts with ``scripts/`` on sys.path.
    sys.path.insert(0, str(_ROOT))

from brain_eleven.infrastructure.locking import (  # noqa: F401,E402
    MemoryStoreLockTimeout,
    file_lock,
)
from brain_eleven.memory import MemoryStore, MemoryStoreCorrupt  # noqa: F401,E402


def _load_canonical(name: str, path: Path) -> ModuleType:
    """Load and cache the package implementation for legacy entrypoints."""

    existing = sys.modules.get(name)
    if existing is not None:
        return existing
    if not path.is_file():
        raise ImportError(f"Cannot load canonical module: {path}")
    module = importlib.import_module(name)
    sys.modules.setdefault(name, module)
    return module


_provenance = _load_canonical(
    "brain_eleven.memory.provenance",
    _ROOT / "brain_eleven" / "memory" / "provenance.py",
)

MemoryProvenance = _provenance.MemoryProvenance
MemoryProvenanceStore = _provenance.MemoryProvenanceStore
PROVENANCE_FILENAME = _provenance.PROVENANCE_FILENAME
PROVENANCE_SCHEMA_VERSION = _provenance.PROVENANCE_SCHEMA_VERSION
ProvenanceCorruptError = _provenance.ProvenanceCorruptError
ProvenanceError = _provenance.ProvenanceError
ProvenanceStoreError = _provenance.ProvenanceStoreError
TimeValue = _provenance.TimeValue
main = _provenance.main
provenance_path = _provenance.provenance_path

__all__ = [
    "MemoryProvenance",
    "MemoryProvenanceStore",
    "PROVENANCE_FILENAME",
    "PROVENANCE_SCHEMA_VERSION",
    "ProvenanceCorruptError",
    "ProvenanceError",
    "ProvenanceStoreError",
    "TimeValue",
    "main",
    "provenance_path",
]

# Preserve the historical bare module name used by direct imports and pytest.
if __name__ == "scripts.memory_provenance":
    sys.modules.setdefault("memory_provenance", sys.modules[__name__])


if __name__ == "__main__":
    raise SystemExit(main())
