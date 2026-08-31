#!/usr/bin/env python3
"""
Brain-Eleven Memory Retriever
Query engine for semantic search over validated memories

Pipeline:
  Query (e.g., "recent architecture decisions")
    ↓
  Search validated-memory.json
    ↓
  Rank by: similarity + freshness + confidence + type priority
    ↓
  Return: top N results with scores
"""

import json
import re
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, asdict
from typing import List, Dict, Tuple, Optional

from memory_scope import filter_memories


@dataclass
class SearchResult:
    """Memory search result with ranking score"""
    id: int
    type: str
    content: str
    confidence: float
    timestamp: str
    similarity: float
    freshness: float
    priority: float
    combined_score: float  # Final ranking score
    memory_id: str = ""


class MemoryRetriever:
    """Query engine for validated memory"""

    # Type priority (decisions > lessons > observations)
    TYPE_PRIORITY = {
        "decision": 1.0,
        "lesson": 0.8,
        "open_loop": 0.9,
        "observation": 0.6
    }

    def __init__(self, vault_path: str):
        self.vault_path = Path(vault_path)
        self.validated_json = self.vault_path / ".claude/validated-memory.json"
        self.memories = []
        self._load_memories()

    def _load_memories(self):
        """Load validated memories from JSON"""
        if not self.validated_json.exists():
            return

        with open(self.validated_json, 'r', encoding='utf-8') as f:
            data = json.load(f)

        self.memories = data.get("validated_memory", [])

    def _similarity_score(self, query: str, text: str) -> float:
        """Word overlap similarity (0.0-1.0)"""
        query_words = set(query.lower().split())
        text_words = set(text.lower().split())

        if not query_words or not text_words:
            return 0.0

        intersection = len(query_words & text_words)
        union = len(query_words | text_words)

        return intersection / union if union > 0 else 0.0

    def _freshness_score(self, timestamp: str) -> float:
        """
        Freshness scoring: newer = higher (0.5-1.0)
        - Same day: 1.0
        - 1 day old: 0.9
        - 7 days old: 0.5
        - Older: 0.3
        """
        try:
            dt = datetime.fromisoformat(timestamp)
            now = datetime.now()
            days_old = (now - dt).days

            if days_old == 0:
                return 1.0
            elif days_old == 1:
                return 0.9
            elif days_old <= 7:
                return max(0.5, 1.0 - (days_old * 0.07))
            else:
                return 0.3
        except:
            return 0.5

    def search(
        self,
        query: str,
        limit: int = 5,
        memories: List[Dict] = None,
        project_id: Optional[str] = None,
        retrieval_scope: str = "default",
    ) -> List[SearchResult]:
        """Search and rank memories (with query relevance filtering)"""

        results = []
        corpus = filter_memories(
            memories if memories is not None else self.memories,
            project_id=project_id,
            retrieval_scope=retrieval_scope,
        )

        for memory in corpus:
            # Skip inactive memories (prevents memory poisoning)
            status = memory.get("status", "active")
            if status != "active":
                continue

            # Calculate similarity (lexical word overlap)
            sim = self._similarity_score(query, memory["content"])

            # Gate: must have at least some query match
            # Prevents low-quality matches from high confidence/freshness scores
            if sim < 0.05:  # Minimum 5% word overlap required
                continue

            fresh = self._freshness_score(memory["timestamp"])
            conf = memory["quality_score"]
            priority = self.TYPE_PRIORITY.get(memory["type"], 0.5)

            # Combined score: weighted average
            # Similarity: 40%, Confidence: 30%, Priority: 20%, Freshness: 10%
            combined = (sim * 0.4) + (conf * 0.3) + (priority * 0.2) + (fresh * 0.1)

            results.append(SearchResult(
                # "id" is the deprecated array-index field kept only for
                # backward compat (see ValidatedMemory.id in
                # memory-validator.py) - a memory missing it should
                # degrade gracefully, not raise KeyError and 500 the
                # whole search request.
                id=memory.get("id", -1),
                type=memory["type"],
                content=memory["content"][:100],  # Truncate for display
                confidence=conf,
                timestamp=memory["timestamp"],
                similarity=sim,
                freshness=fresh,
                priority=priority,
                combined_score=combined,
                memory_id=memory.get("memory_id", "")
            ))

        # Sort by combined score
        results.sort(key=lambda r: r.combined_score, reverse=True)

        return results[:limit]

    def get_by_type(
        self,
        memory_type: str,
        limit: int = 5,
        project_id: Optional[str] = None,
        retrieval_scope: str = "default",
    ) -> List[SearchResult]:
        """Get top memories of a specific type"""

        results = []

        for memory in filter_memories(
            self.memories,
            project_id=project_id,
            retrieval_scope=retrieval_scope,
        ):
            if memory["type"] != memory_type:
                continue

            fresh = self._freshness_score(memory["timestamp"])
            conf = memory["quality_score"]

            results.append(SearchResult(
                # "id" is the deprecated array-index field kept only for
                # backward compat (see ValidatedMemory.id in
                # memory-validator.py) - a memory missing it should
                # degrade gracefully, not raise KeyError and 500 the
                # whole search request.
                id=memory.get("id", -1),
                type=memory["type"],
                content=memory["content"][:100],
                confidence=conf,
                timestamp=memory["timestamp"],
                similarity=1.0,  # Type match
                freshness=fresh,
                priority=1.0,
                combined_score=(conf * 0.6) + (fresh * 0.4),
                memory_id=memory.get("memory_id", ""),
            ))

        results.sort(key=lambda r: r.combined_score, reverse=True)
        return results[:limit]

    def format_results(self, results: List[SearchResult]) -> str:
        """Format search results for display"""

        if not results:
            return "No results found."

        lines = []
        for i, r in enumerate(results, 1):
            lines.append(
                f"{i}. [{r.type.upper()}] (score: {r.combined_score:.2f})"
            )
            lines.append(f"   {r.content}...")
            lines.append(f"   Confidence: {r.confidence:.2f}, Freshness: {r.freshness:.2f}")
            lines.append("")

        return "\n".join(lines)


# ============================================================================
# CLI
# ============================================================================

if __name__ == "__main__":
    import sys

    vault_path = Path.home() / "Documents/Brain-Eleven"
    retriever = MemoryRetriever(str(vault_path))

    if len(sys.argv) > 1:
        query = " ".join(sys.argv[1:])
        print(f"\n🔍 Searching for: {query}\n")

        results = retriever.search(query)
        print(retriever.format_results(results))

        # Also output JSON for programmatic use
        output_file = vault_path / ".claude/search-results.json"
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(
                {
                    "query": query,
                    "results": [asdict(r) for r in results],
                    "timestamp": datetime.now().isoformat()
                },
                f,
                indent=2,
                ensure_ascii=False
            )
        print(f"\n📁 Results saved to: {output_file}")

    else:
        print("Usage: memory-retriever.py <query>")
        print("Example: memory-retriever.py 'recent architecture decisions'")
