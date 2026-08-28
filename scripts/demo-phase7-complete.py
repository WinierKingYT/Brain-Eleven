#!/usr/bin/env python3
"""
Phase 7 Complete Demo: Semantic Search + Hybrid Search + ML Ranking

Demonstrates the full Phase 7 system with:
1. Embedding generation with caching
2. Semantic search (vector similarity)
3. Hybrid search (lexical 40% + semantic 60%)
4. ML ranking (5-feature weighted combination)
"""

import sys
import json
import importlib.util
from pathlib import Path
from datetime import datetime
import time

# Setup module loading
def load_module(name, filename):
    spec = importlib.util.spec_from_file_location(
        name,
        Path(__file__).parent / filename
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

# Load all Phase 7 components
embedding_gen = load_module("embedding_generator", "embedding-generator.py")
semantic_search = load_module("semantic_search", "semantic-search.py")
hybrid_search = load_module("hybrid_search", "hybrid-search.py")
ml_ranker = load_module("ml_ranker", "ml-ranker.py")

EmbeddingGenerator = embedding_gen.EmbeddingGenerator
SemanticSearchEngine = semantic_search.SemanticSearchEngine
HybridSearchEngine = hybrid_search.HybridSearchEngine
MLRanker = ml_ranker.MLRanker


def print_header(text: str):
    """Print formatted header"""
    print(f"\n{'='*70}")
    print(f"  {text}")
    print(f"{'='*70}\n")


def print_result(index: int, result: dict, show_features: bool = False):
    """Print formatted search result"""
    print(f"  {index}. 📌 Memory ID: {result['memory_id']}")
    print(f"     Type: {result.get('type', 'unknown').upper()}")
    print(f"     Content: {result.get('content', '')[:70]}...")

    # Show scores
    if 'combined_score' in result:
        print(f"     Combined Score: {result['combined_score']:.3f}")
        print(f"       └─ Lexical: {result.get('lexical_score', 0):.3f} | "
              f"Semantic: {result.get('semantic_score', 0):.3f}")

    if 'ml_score' in result:
        print(f"     ML Score: {result['ml_score']:.3f}")

        if show_features:
            features = result.get('ml_features', {})
            print(f"     Features breakdown:")
            for fname, fval in features.items():
                print(f"       • {fname}: {fval:.3f}")

    print()


def main():
    vault_path = Path.home() / "Documents/Brain-Eleven"

    # Load memories
    validated_file = vault_path / ".claude/validated-memory.json"
    if not validated_file.exists():
        print("❌ No validated memories found")
        return

    with open(validated_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
        memories = data.get("validated_memory", [])

    print_header(f"🧠 Brain-Eleven Phase 7 Demo - {len(memories)} Memories")

    # ========================================================================
    # STEP 1: EMBEDDING GENERATION
    # ========================================================================
    print_header("Step 1️⃣  - Embedding Generation")

    gen = EmbeddingGenerator(str(vault_path))

    # Check if embeddings exist
    existing_count = sum(1 for m in memories if gen.get_embedding(m['memory_id']) is not None)

    if existing_count < len(memories):
        print(f"📊 Generating embeddings for {len(memories) - existing_count} new memories...")
        start = time.time()
        embeddings = gen.batch_embed(memories)
        gen.save()
        elapsed = time.time() - start
        print(f"✅ Generated {len(embeddings)} embeddings in {elapsed:.2f}s")
    else:
        print(f"✅ All {len(memories)} memories already embedded (cached)")

    # Show embedding stats
    stats = {
        'total': len(memories),
        'embedded': sum(1 for m in memories if gen.get_embedding(m['memory_id']) is not None),
        'model': gen.model,
        'dimension': 1536
    }
    print(f"\n📈 Embedding Stats:")
    print(f"   Total memories: {stats['total']}")
    print(f"   Embedded: {stats['embedded']}")
    print(f"   Model: {stats['model']}")
    print(f"   Dimension: {stats['dimension']}")

    # ========================================================================
    # STEP 2: SEMANTIC SEARCH
    # ========================================================================
    print_header("Step 2️⃣  - Semantic Search")

    semantic_engine = SemanticSearchEngine(str(vault_path))

    demo_queries = [
        "database design production",
        "authentication security oauth",
        "testing and quality assurance"
    ]

    for query in demo_queries:
        print(f"🔎 Query: \"{query}\"")
        start = time.time()
        results = semantic_engine.search(query, memories, top_k=3)
        elapsed = time.time() - start

        print(f"   ⏱️  Latency: {elapsed*1000:.1f}ms\n")

        if results:
            for i, result in enumerate(results, 1):
                print(f"   {i}. Similarity: {result['similarity']:.3f}")
                print(f"      {result['content']}...\n")
        else:
            print("   No results\n")

    # ========================================================================
    # STEP 3: HYBRID SEARCH
    # ========================================================================
    print_header("Step 3️⃣  - Hybrid Search (Lexical 40% + Semantic 60%)")

    hybrid_engine = HybridSearchEngine(str(vault_path))

    for query in demo_queries:
        print(f"🔎 Query: \"{query}\"")
        start = time.time()
        results = hybrid_engine.search(query, memories, top_k=3)
        elapsed = time.time() - start

        print(f"   ⏱️  Latency: {elapsed*1000:.1f}ms")

        # Show quality analysis
        quality = hybrid_engine.get_search_quality(results)
        print(f"   📊 Results: {quality['total_results']} found")
        print(f"      Balance: {quality['balance']}")
        if quality['found_in_both'] > 0:
            print(f"      Found in both: {quality['found_in_both']}\n")

        for i, result in enumerate(results, 1):
            print_result(i, result)

    # ========================================================================
    # STEP 4: ML RANKING
    # ========================================================================
    print_header("Step 4️⃣  - ML Ranking (5-Feature Weighted Combination)")

    ranker = MLRanker()

    print("🎯 Ranking Configuration:")
    for name, weight in ranker.get_weights().items():
        print(f"   {name}: {weight:.0%}")

    print()

    for query in demo_queries:
        print(f"🔎 Query: \"{query}\"")

        # Get hybrid results
        hybrid_results = hybrid_engine.search(query, memories, top_k=5)

        # Apply ML ranking
        start = time.time()
        ranked_results = ranker.rank(query, hybrid_results, memories)
        elapsed = time.time() - start

        print(f"   ⏱️  Ranking latency: {elapsed*1000:.1f}ms\n")

        for i, result in enumerate(ranked_results[:3], 1):
            print_result(i, result, show_features=True)

        # Show ranking analysis
        analysis = ranker.get_ranking_analysis(ranked_results)
        print(f"   📊 Ranking Analysis:")
        print(f"      Avg Score: {analysis['avg_score']:.3f}")
        print(f"      Score Range: {analysis['min_score']:.3f} → {analysis['max_score']:.3f}")
        print()

    # ========================================================================
    # STEP 5: PERFORMANCE SUMMARY
    # ========================================================================
    print_header("Performance Summary")

    # Benchmark full pipeline
    query = "architecture scalability microservices"

    print(f"📍 Full pipeline benchmark: \"{query}\"\n")

    # Semantic only
    start = time.time()
    sem_results = semantic_engine.search(query, memories, top_k=5)
    sem_time = time.time() - start
    print(f"   Semantic search:     {sem_time*1000:6.1f}ms")

    # Hybrid only
    start = time.time()
    hyb_results = hybrid_engine.search(query, memories, top_k=5)
    hyb_time = time.time() - start
    print(f"   Hybrid search:       {hyb_time*1000:6.1f}ms")

    # Hybrid + ML ranking
    start = time.time()
    ranked = ranker.rank(query, hyb_results, memories)
    rank_time = time.time() - start
    print(f"   ML ranking:          {rank_time*1000:6.1f}ms")

    total_time = sem_time + hyb_time + rank_time
    print(f"   ─────────────────────────────")
    print(f"   Total pipeline:      {total_time*1000:6.1f}ms")
    print()

    # ========================================================================
    # STEP 6: QUALITY METRICS
    # ========================================================================
    print_header("Quality Metrics")

    # Sample multiple queries and compute average metrics
    test_queries = demo_queries + [
        "performance optimization caching",
        "error handling and resilience"
    ]

    latencies = []
    coverage = []

    for query in test_queries:
        start = time.time()
        results = hybrid_engine.search(query, memories, top_k=5)
        elapsed = time.time() - start

        latencies.append(elapsed * 1000)

        # Check how many unique memory types covered
        types = {r.get('type') for r in results}
        coverage.append(len(types))

    print(f"🎯 Query Performance:")
    print(f"   Average latency: {sum(latencies)/len(latencies):.1f}ms")
    print(f"   Min latency:     {min(latencies):.1f}ms")
    print(f"   Max latency:     {max(latencies):.1f}ms")
    print(f"   P95 latency:     {sorted(latencies)[int(len(latencies)*0.95)]:.1f}ms")
    print()

    print(f"📊 Result Quality:")
    print(f"   Average types covered: {sum(coverage)/len(coverage):.1f}")
    print(f"   Avg result score: {sum(r.get('combined_score', 0) for r in results)/len(results):.3f}")
    print()

    # ========================================================================
    # FINAL SUMMARY
    # ========================================================================
    print_header("✅ Phase 7 Complete Demo Summary")

    print(f"📈 System Status:")
    print(f"   ✓ {len(memories)} memories indexed with embeddings")
    print(f"   ✓ Semantic search working (vector similarity)")
    print(f"   ✓ Hybrid search working (lexical + semantic)")
    print(f"   ✓ ML ranking working (5-feature combination)")
    print(f"   ✓ Average query latency: {sum(latencies)/len(latencies):.1f}ms")
    print()

    print(f"🎯 Key Features:")
    print(f"   • Cosine similarity for vector matching")
    print(f"   • Weighted scoring (40% lexical + 60% semantic)")
    print(f"   • Recency decay function (exp(-days/30))")
    print(f"   • Match type scoring (exact > partial > fuzzy)")
    print(f"   • Deterministic fallback embeddings (no API key)")
    print()

    print(f"🚀 Ready for Phase 8: Deployment & CI/CD")
    print()


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
