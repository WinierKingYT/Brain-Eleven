#!/usr/bin/env python3
"""
Brain-Eleven Semantic Search Engine
Vector-based similarity matching for memory retrieval

Uses cosine similarity to find semantically similar memories
to a query, independent of exact keyword matches.
"""

import json
import numpy as np
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional

# Import our modules
import sys
sys.path.insert(0, str(Path(__file__).parent))

import importlib.util
spec = importlib.util.spec_from_file_location(
    "embedding_generator",
    Path(__file__).parent / "embedding-generator.py"
)
embedding_generator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(embedding_generator)
EmbeddingGenerator = embedding_generator.EmbeddingGenerator


class SemanticSearchEngine:
    """Semantic similarity search using vector embeddings"""

    def __init__(self, vault_path: str):
        self.vault_path = Path(vault_path)
        self.generator = EmbeddingGenerator(str(vault_path))

    # ========================================================================
    # SEARCH OPERATIONS
    # ========================================================================

    def search(self, query: str, memories: List[Dict], top_k: int = 5) -> List[Dict]:
        """Search using semantic similarity"""

        # Generate query embedding
        query_embedding = self.generator.embed_text(query)

        # Compute similarity with all memories
        similarities = []

        for memory in memories:
            # Skip if no embedding
            memory_id = memory.get("memory_id")
            if not memory_id:
                continue

            # Get cached embedding
            embedding = self.generator.get_embedding(memory_id)
            if embedding is None:
                continue

            # Compute cosine similarity
            similarity = self._cosine_similarity(query_embedding, embedding)

            similarities.append({
                'memory_id': memory_id,
                'similarity': float(similarity),
                'type': 'semantic',
                'content': memory.get('content', '')[:60],
                'memory_type': memory.get('type', 'unknown')
            })

        # Sort by similarity
        similarities.sort(key=lambda x: x['similarity'], reverse=True)

        return similarities[:top_k]

    # ========================================================================
    # SIMILARITY COMPUTATION
    # ========================================================================

    @staticmethod
    def _cosine_similarity(v1: np.ndarray, v2: np.ndarray) -> float:
        """Cosine similarity between two vectors"""

        # Compute dot product
        dot_product = np.dot(v1, v2)

        # Compute norms
        norm_v1 = np.linalg.norm(v1)
        norm_v2 = np.linalg.norm(v2)

        # Avoid division by zero
        if norm_v1 == 0 or norm_v2 == 0:
            return 0.0

        # Cosine similarity
        return dot_product / (norm_v1 * norm_v2)

    # ========================================================================
    # BATCH SEARCH
    # ========================================================================

    def batch_search(self, queries: List[str], memories: List[Dict], top_k: int = 5) -> Dict[str, List]:
        """Execute multiple searches"""

        results = {}

        for query in queries:
            print(f"🔍 Searching: {query[:50]}...")
            results[query] = self.search(query, memories, top_k)

        return results

    # ========================================================================
    # EMBEDDING MANAGEMENT
    # ========================================================================

    def regenerate_embeddings(self, memories: List[Dict]):
        """Regenerate embeddings for memories"""

        print(f"🔄 Regenerating embeddings for {len(memories)} memories...")

        embeddings = self.generator.batch_embed(memories)
        self.generator.save()

        print(f"✅ Regenerated {len(embeddings)} embeddings")

    def get_embedding_stats(self) -> Dict:
        """Get statistics about embeddings"""

        embeddings_dict = self.generator.embeddings

        if not embeddings_dict:
            return {"total": 0, "model": "none"}

        # Get sample embedding to check dimension
        sample = list(embeddings_dict.values())[0]
        dimension = len(sample) if isinstance(sample, list) else 0

        return {
            "total_embeddings": len(embeddings_dict),
            "model": self.generator.model,
            "dimension": dimension,
            "cache_file": str(self.generator.embedding_cache)
        }


# ============================================================================
# CLI & DEMO
# ============================================================================

if __name__ == "__main__":
    import sys

    vault_path = Path.home() / "Documents/Brain-Eleven"

    # Load memories
    validated_file = vault_path / ".claude/validated-memory.json"
    if not validated_file.exists():
        print("❌ No validated memories found")
        sys.exit(1)

    with open(validated_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
        memories = data.get("validated_memory", [])

    print(f"📚 Loaded {len(memories)} memories")

    # Initialize search engine
    engine = SemanticSearchEngine(str(vault_path))

    # Show stats
    stats = engine.get_embedding_stats()
    print(f"\n📊 Embedding Statistics:")
    print(f"   Total embeddings: {stats['total_embeddings']}")
    print(f"   Model: {stats['model']}")
    print(f"   Dimension: {stats['dimension']}")

    # If no embeddings, generate them
    if stats['total_embeddings'] == 0:
        print("\n🚀 No embeddings found, generating...")
        engine.regenerate_embeddings(memories)
        stats = engine.get_embedding_stats()
        print(f"✅ Generated {stats['total_embeddings']} embeddings")

    # Demo searches
    demo_queries = [
        "PostgreSQL database",
        "API design patterns",
        "testing and quality",
        "authentication security",
        "performance optimization"
    ]

    print(f"\n🔍 Running demo searches...\n")

    for query in demo_queries:
        results = engine.search(query, memories, top_k=3)

        print(f"Query: \"{query}\"")
        if results:
            for i, result in enumerate(results, 1):
                print(f"  {i}. [{result['memory_type'].upper()}] {result['similarity']:.3f}")
                print(f"     {result['content']}...")
        else:
            print("  No results")
        print()

    print("✅ Semantic search demo complete")
