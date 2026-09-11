#!/usr/bin/env python3
"""Compatibility/direct-execution adapter for the graph projection."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from types import ModuleType


_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    # Historical direct execution starts with ``scripts/`` on sys.path.
    sys.path.insert(0, str(_ROOT))


# Keep the migration contract explicit: the adapter uses packaged memory
# dependencies and never reaches a legacy store implementation.
from brain_eleven.memory import (  # noqa: F401,E402
    MemoryStore,
    MemoryStoreError,
    infer_memory_scope,
)


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


_projection = _load_canonical(
    "brain_eleven.graph.projection",
    _ROOT / "brain_eleven" / "graph" / "projection.py",
)

KNOWLEDGE_GRAPH_SCHEMA_VERSION = _projection.KNOWLEDGE_GRAPH_SCHEMA_VERSION
KnowledgeGraphProjectionError = _projection.KnowledgeGraphProjectionError
KnowledgeGraphProjectionStale = _projection.KnowledgeGraphProjectionStale
KnowledgeGraph = _projection.KnowledgeGraph
_utc_now = _projection._utc_now
main = _projection.main
logger = _projection.logger

__all__ = [
    "KNOWLEDGE_GRAPH_SCHEMA_VERSION",
    "KnowledgeGraph",
    "KnowledgeGraphProjectionError",
    "KnowledgeGraphProjectionStale",
    "_utc_now",
    "main",
    "logger",
]


# Preserve the historical bare module name used by direct imports and pytest.
if __name__ == "scripts.knowledge_graph":
    sys.modules.setdefault("knowledge_graph", _projection)


if __name__ == "__main__":
    raise SystemExit(main())
