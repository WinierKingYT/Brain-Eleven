"""Public boundary for the derived knowledge-graph projection."""

from .projection import (
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
