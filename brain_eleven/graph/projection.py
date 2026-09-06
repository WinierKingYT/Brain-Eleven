"""Identity-preserving package surface for the derived graph projection.

The implementation remains in ``scripts/knowledge_graph.py`` while the
repository is consolidated incrementally.  Re-exporting the exact objects
keeps graph callers on one implementation without changing projection,
revision, or persistence semantics.
"""

from __future__ import annotations

import sys
from pathlib import Path


_ROOT = Path(__file__).resolve().parents[2]
_SCRIPTS = _ROOT / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from knowledge_graph import (  # noqa: E402
    KNOWLEDGE_GRAPH_SCHEMA_VERSION,
    KnowledgeGraph,
    KnowledgeGraphProjectionError,
    KnowledgeGraphProjectionStale,
)

__all__ = [
    "KNOWLEDGE_GRAPH_SCHEMA_VERSION",
    "KnowledgeGraph",
    "KnowledgeGraphProjectionError",
    "KnowledgeGraphProjectionStale",
]
