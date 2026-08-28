#!/usr/bin/env python3
"""
Brain-Eleven Hybrid Search Engine
Combine lexical + semantic search for optimal retrieval

Lexical (40%): Exact keyword matching, good for specific queries
Semantic (60%): Meaning-based matching, good for conceptual queries

Together: Best of both worlds
"""

import json
import numpy as np
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional

import sys
sys.path.insert(0, str(Path(__file__).parent))

import importlib.util

# Load semantic search
spec = importlib.util.spec_from_file_location(
    "semantic_search",
    Path(__file__).parent / "semantic-search.py"
)
semantic_search_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(semantic_search_module)
SemanticSearchEngine = semantic_search_module.SemanticSearchEngine

# Load retriever (Phase 4)
spec = importlib.util.spec_from_file_location(
    "memory_retriever",
    Path(__file__).parent / "memory-retriever.py"
)
memory_retriever = importlib.util.module_from_spec(spec)
spec.loader.exec_module(memory_retriever)
MemoryRetriever = memory_retriever.MemoryRetriever


class HybridSearchEngine:
    """Hybrid search combining lexical and semantic methods"""

    def __init__(self, vault_path: str):
        self.vault_path = Path(vault_path)
        self.semantic = SemanticSearchEngine(vault_path)
        self.lexical = MemoryRetriever(vault_path)

        # Hybrid weights
        self.lexical_weight = 0.40
        self.semantic_weight = 0.60

    # ========================================================================
    # HYBRID SEARCH
    # ========================================================================

    def search(self, query: str, memories: List[Dict], top_k: int = 5) -> List[Dict]:
        """Execute hybrid search: lexical + semantic"""

        print(f"\n🔎 Hybrid search: \"{query}\"")

        # Get lexical results (Phase 4 retriever)
        print(f"   → Lexical search...")
        lexical_results = self.lexical.retrieve(query, memories, top_k=10)

        # Get semantic results
        print(f"   → Semantic search...")
        semantic_results = self.semantic.search(query, memories, top_k=10)

        # Merge and combine scores
        merged = self._merge_results(query, lexical_results, semantic_results, memories)

        # Sort by combined score
        merged.sort(key=lambda x: x['combined_score'], reverse=True)

        print(f"   ✅ Found {len(merged)} candidates, top {min(top_k, len(merged))} ranked")

        return merged[:top_k]

    # ========================================================================
    # RESULT MERGING & SCORING
    # ========================================================================

    def _merge_results(
        self,
        query: str,
        lexical: List[Dict],
        semantic: List[Dict],
        memories: List[Dict]
    ) -> List[Dict]:
        """Merge lexical and semantic results"""

        combined = {}

        # Process lexical results (40% weight)
        for rank, result in enumerate(lexical):
            mem_id = result.get('memory_id')
            if not mem_id:
                continue

            # Normalize lexical score (0-1 range)
            lex_score = result.get('score', 0) / 1.0  # Already normalized from retriever

            combined[mem_id] = {
                'memory_id': mem_id,
                'lexical_score': lex_score,
                'lexical_rank': rank,
                'semantic_score': 0.0,
                'semantic_rank': 999,
                'combined_score': 0.0,
                'search_type': 'lexical'
            }

        # Process semantic results (60% weight)
        for rank, result in enumerate(semantic):
            mem_id = result.get('memory_id')
            if not mem_id:
                continue

            sem_score = result.get('similarity', 0)  # Already 0-1 from embeddings

            if mem_id in combined:
                # Update existing (found in both)
                combined[mem_id]['semantic_score'] = sem_score
                combined[mem_id]['semantic_rank'] = rank
                combined[mem_id]['search_type'] = 'both'
            else:
                # New result (semantic only)
                combined[mem_id] = {
                    'memory_id': mem_id,
                    'lexical_score': 0.0,
                    'lexical_rank': 999,
                    'semantic_score': sem_score,
                    'semantic_rank': rank,
                    'combined_score': 0.0,
                    'search_type': 'semantic'
                }

        # Compute combined scores
        for mem_id, item in combined.items():
            # Weighted combination: 40% lexical + 60% semantic
            combined_score = (
                (item['lexical_score'] * self.lexical_weight) +
                (item['semantic_score'] * self.semantic_weight)
            )

            # Apply freshness boost
            memory = next((m for m in memories if m['memory_id'] == mem_id), None)
            if memory:
                item['quality_score'] = memory.get('quality_score', 0.5)
                combined_score *= (1.0 + (memory.get('novelty', 0.5) * 0.1))
            else:
                item['quality_score'] = 0.5

            item['combined_score'] = combined_score

        return list(combined.values())

    # ========================================================================
    # SEARCH STATISTICS
    # ========================================================================

    def get_search_quality(self, results: List[Dict]) -> Dict:
        """Analyze search result quality"""

        if not results:
            return {"quality": 0, "balance": "none"}

        # Count by search type
        both = sum(1 for r in results if r.get('search_type') == 'both')
        lexical = sum(1 for r in results if r.get('search_type') == 'lexical')
        semantic = sum(1 for r in results if r.get('search_type') == 'semantic')

        # Average scores
        avg_combined = np.mean([r['combined_score'] for r in results]) if results else 0
        avg_lex = np.mean([r['lexical_score'] for r in results if r['lexical_score'] > 0]) if lexical else 0
        avg_sem = np.mean([r['semantic_score'] for r in results if r['semantic_score'] > 0]) if semantic else 0

        return {
            "quality": avg_combined,
            "total_results": len(results),
            "found_in_both": both,
            "lexical_only": lexical,
            "semantic_only": semantic,
            "avg_lexical_score": avg_lex,
            "avg_semantic_score": avg_sem,
            "balance": "balanced" if both > 0 else ("lexical-heavy" if lexical > semantic else "semantic-heavy")
        }


# ============================================================================
# CLI & DEMO
# ============================================================================

if __name__ == "__main__":
    vault_path = Path.home() / "Documents/Brain-Eleven"

    # Load memories
    validated_file = vault_path / ".claude/validated-memory.json"
    if not validated_file.exists():
        print("❌ No validated memories found")
        sys.exit(1)

    with open(validated_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
        memories = data.get("validated_memory", [])

    print(f"📚 Loaded {len(memories)} memories for hybrid search")

    # Initialize hybrid search
    engine = HybridSearchEngine(str(vault_path))

    # Demo searches
    demo_queries = [
        "database design for production",
        "how to implement authentication",
        "testing strategies and best practices",
        "performance optimization techniques",
        "microservices vs monolithic architecture"
    ]

    print(f"\n🔍 Running hybrid search demos...\n")
    print("=" * 70)

    for query in demo_queries:
        results = engine.search(query, memories, top_k=3)

        print(f"\nQuery: \"{query}\"")
        print(f"Results: {len(results)} found\n")

        if results:
            for i, result in enumerate(results, 1):
                print(f"  {i}. Combined Score: {result['combined_score']:.3f}")
                print(f"     Lexical: {result['lexical_score']:.3f} | Semantic: {result['semantic_score']:.3f}")
                print(f"     Type: {result['search_type'].upper()}")
                print(f"     Quality: {result.get('quality_score', 0):.2f}")
                print()

        # Quality analysis
        quality = engine.get_search_quality(results)
        print(f"  Analysis: {quality['balance']} ({quality['found_in_both']} in both, "
              f"{quality['lexical_only']} lexical, {quality['semantic_only']} semantic)")
        print()

    print("=" * 70)
    print("✅ Hybrid search demo complete")
