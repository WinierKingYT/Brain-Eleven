"""Stable package boundary for the legacy search implementations.

The search behavior remains unchanged during PRE-12.  The package exposes
the existing lexical, hybrid, and ranking classes from one cached loading
surface so API and chat callers cannot accidentally fork the implementation.
"""

from __future__ import annotations

from brain_eleven._legacy import load_legacy_module


_memory_retriever = load_legacy_module("memory_retriever", "memory-retriever.py")
_hybrid_search = load_legacy_module("hybrid_search", "hybrid-search.py")
_ml_ranker = load_legacy_module("ml_ranker", "ml-ranker.py")

SearchResult = _memory_retriever.SearchResult
MemoryRetriever = _memory_retriever.MemoryRetriever
HybridSearchEngine = _hybrid_search.HybridSearchEngine
MLRanker = _ml_ranker.MLRanker

__all__ = [
    "HybridSearchEngine",
    "MLRanker",
    "MemoryRetriever",
    "SearchResult",
]

