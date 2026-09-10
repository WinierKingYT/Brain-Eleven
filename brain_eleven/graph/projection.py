"""Identity-preserving package surface for the derived graph projection.

The implementation remains in ``scripts/knowledge_graph.py`` while the
repository is consolidated incrementally.  Re-exporting the exact objects
keeps graph callers on one implementation without changing projection,
revision, or persistence semantics.
"""

from __future__ import annotations

from scripts.knowledge_graph import (
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
