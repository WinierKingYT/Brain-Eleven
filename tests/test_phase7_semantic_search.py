#!/usr/bin/env python3
"""
Phase 7: Semantic Search & ML Ranking Tests
Test embedding generation, semantic search, hybrid search, and ML ranking
"""

import sys
import importlib.util
from pathlib import Path
import pytest
import json
import numpy as np
from datetime import datetime, timedelta
from types import SimpleNamespace

# Setup path

# Load modules with importlib
def load_module(name, filename):
    spec = importlib.util.spec_from_file_location(
        name,
        Path(__file__).parent.parent / "scripts" / filename
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

embedding_gen = load_module("embedding_generator", "embedding-generator.py")
semantic_search = load_module("semantic_search", "semantic-search.py")
hybrid_search = load_module("hybrid_search", "hybrid-search.py")
ml_ranker = load_module("ml_ranker", "ml-ranker.py")

EmbeddingGenerator = embedding_gen.EmbeddingGenerator
SemanticSearchEngine = semantic_search.SemanticSearchEngine
HybridSearchEngine = hybrid_search.HybridSearchEngine
MLRanker = ml_ranker.MLRanker


def enable_fake_provider(generator):
    """Enable a deterministic in-process provider for structural tests only."""

    class FakeEmbeddings:
        def create(self, *, input, model):
            vector = generator._embed_fallback(input).tolist()
            return SimpleNamespace(data=[SimpleNamespace(embedding=vector)])

    generator.use_openai = True
    generator.client = SimpleNamespace(embeddings=FakeEmbeddings())
    return generator


def enable_controlled_provider(generator):
    """Provide a tiny semantic oracle so ranking tests include a distractor."""

    def vector_for(text):
        lowered = text.casefold()
        vector = np.zeros(1536, dtype=np.float32)
        if any(token in lowered for token in ("postgres", "database", "relational", "datastore")):
            vector[0] = 1.0
        elif any(token in lowered for token in ("marketing", "color", "logo")):
            vector[1] = 1.0
        else:
            vector[2] = 1.0
        return vector.tolist()

    class ControlledEmbeddings:
        def create(self, *, input, model):
            return SimpleNamespace(data=[SimpleNamespace(embedding=vector_for(input))])

    generator.use_openai = True
    generator.client = SimpleNamespace(embeddings=ControlledEmbeddings())
    return generator


@pytest.fixture
def temp_vault(tmp_path):
    """Create temporary vault for testing"""
    vault_path = tmp_path / "test-vault"
    vault_path.mkdir()
    (vault_path / ".claude").mkdir()
    return vault_path


@pytest.fixture
def sample_memories(temp_vault):
    """Create sample memories with timestamps"""
    return [
        {
            "memory_id": "01M155WB9AKKTCZWTFRDDZR4W7",
            "type": "decision",
            "content": "Use PostgreSQL for production database",
            "confidence": 0.95,
            "quality_score": 0.95,
            "novelty": 0.8,
            "timestamp": (datetime.now() - timedelta(days=5)).isoformat(),
            "status": "active"
        },
        {
            "memory_id": "01M155WB9FCSPSFQCFM8NVATS8",
            "type": "lesson",
            "content": "API design requires careful planning and testing",
            "confidence": 0.85,
            "quality_score": 0.85,
            "novelty": 0.7,
            "timestamp": (datetime.now() - timedelta(days=2)).isoformat(),
            "status": "active"
        },
        {
            "memory_id": "01M155WB9FCSPSFQCFM8NVATSD",
            "type": "open_loop",
            "content": "Implement user authentication with OAuth2",
            "confidence": 0.90,
            "quality_score": 0.90,
            "novelty": 0.6,
            "timestamp": (datetime.now() - timedelta(hours=1)).isoformat(),
            "status": "active"
        },
        {
            "memory_id": "01M156CKJAWDPFCPV7RZ011QC0",
            "type": "decision",
            "content": "Use microservices architecture for scalability",
            "confidence": 0.80,
            "quality_score": 0.80,
            "novelty": 0.5,
            "timestamp": (datetime.now() - timedelta(days=10)).isoformat(),
            "status": "active"
        }
    ]


class TestEmbeddingGenerator:
    """Test embedding generation and caching"""

    def test_embed_text_unavailable_without_provider(self, temp_vault):
        """No provider must not produce a fake semantic vector."""
        generator = EmbeddingGenerator(str(temp_vault))

        text = "Test embedding generation"
        embedding = generator.embed_text(text)

        assert embedding is None
        assert generator.semantic_available is False

    def test_embed_deterministic(self, temp_vault):
        """Test that embeddings are deterministic"""
        generator = enable_fake_provider(EmbeddingGenerator(str(temp_vault)))

        text = "Deterministic test"
        emb1 = generator.embed_text(text)
        emb2 = generator.embed_text(text)

        # Same text should produce same embedding
        assert np.allclose(emb1, emb2, atol=1e-6)

    def test_batch_embed(self, temp_vault, sample_memories):
        """Test batch embedding"""
        generator = enable_fake_provider(EmbeddingGenerator(str(temp_vault)))

        embeddings = generator.batch_embed(sample_memories)

        # Should embed all memories
        assert len(embeddings) == len(sample_memories)

        # Each should be correct dimension
        for mem_id, emb in embeddings.items():
            assert emb.shape == (1536,)

    def test_cache_persistence(self, temp_vault, sample_memories):
        """Test that embeddings are cached"""
        generator = enable_fake_provider(EmbeddingGenerator(str(temp_vault)))

        # First run
        embeddings = generator.batch_embed(sample_memories[:2])
        generator.save()

        # Second run - should use cache
        generator2 = enable_fake_provider(EmbeddingGenerator(str(temp_vault)))
        cached_emb = generator2.get_embedding(
            sample_memories[0]["memory_id"], sample_memories[0]["content"]
        )

        # Should have cached value
        assert cached_emb is not None
        assert cached_emb.shape == (1536,)

    def test_cache_rejects_content_mutation(self, temp_vault, sample_memories):
        generator = enable_fake_provider(EmbeddingGenerator(str(temp_vault)))
        generator.batch_embed(sample_memories[:1])

        changed = sample_memories[0]["content"] + " (changed)"
        assert generator.get_embedding(sample_memories[0]["memory_id"], changed) is None

    def test_cache_rejects_source_revision_mutation(self, temp_vault, sample_memories):
        generator = enable_fake_provider(EmbeddingGenerator(str(temp_vault)))
        memory = dict(sample_memories[0], source_revision=4)
        generator.batch_embed([memory])

        assert generator.get_embedding(memory["memory_id"], memory["content"], source_revision=4) is not None
        assert generator.get_embedding(memory["memory_id"], memory["content"], source_revision=5) is None

    def test_cache_rejects_provider_transition(self, temp_vault, sample_memories):
        generator = enable_fake_provider(EmbeddingGenerator(str(temp_vault)))
        generator.batch_embed(sample_memories[:1])
        generator.save()

        unavailable = EmbeddingGenerator(str(temp_vault))
        assert unavailable.get_embedding(sample_memories[0]["memory_id"], sample_memories[0]["content"]) is None


class TestSemanticSearch:
    """Test semantic similarity search"""

    def test_cosine_similarity(self):
        """Test cosine similarity computation"""
        # Create test vectors
        v1 = np.array([1, 0, 0], dtype=np.float32)
        v2 = np.array([1, 0, 0], dtype=np.float32)
        v3 = np.array([0, 1, 0], dtype=np.float32)

        engine = SemanticSearchEngine.__new__(SemanticSearchEngine)

        # Same vector = 1.0
        sim_same = engine._cosine_similarity(v1, v2)
        assert abs(sim_same - 1.0) < 0.001

        # Orthogonal vectors = 0.0
        sim_ortho = engine._cosine_similarity(v1, v3)
        assert abs(sim_ortho) < 0.001

    def test_semantic_search_no_embeddings(self, temp_vault, sample_memories):
        """Test semantic search when no embeddings exist"""
        engine = SemanticSearchEngine(str(temp_vault))

        results = engine.search("database", sample_memories, top_k=3)

        # Should return empty or handle gracefully
        assert isinstance(results, list)

    def test_search_returns_top_k(self, temp_vault, sample_memories):
        """Test that search returns top_k results"""
        engine = SemanticSearchEngine(str(temp_vault))

        # Generate embeddings first
        engine.generator.batch_embed(sample_memories)

        results = engine.search("database", sample_memories, top_k=2)

        # Should return at most top_k
        assert len(results) <= 2

    def test_semantic_ranking_prefers_paraphrase_over_unrelated_distractor(self, temp_vault):
        memories = [
            {"memory_id": "db", "content": "PostgreSQL is the production database", "type": "decision"},
            {"memory_id": "noise", "content": "The marketing logo uses a blue color", "type": "preference"},
        ]
        engine = SemanticSearchEngine(str(temp_vault))
        enable_controlled_provider(engine.generator).batch_embed(memories)

        results = engine.search("Which relational datastore is canonical?", memories, top_k=2)

        assert [item["memory_id"] for item in results] == ["db", "noise"]
        assert results[0]["similarity"] > results[1]["similarity"]


class TestHybridSearch:
    """Test hybrid lexical + semantic search"""

    def test_hybrid_search_merge(self, temp_vault, sample_memories):
        """Test merging lexical and semantic results"""
        engine = HybridSearchEngine(str(temp_vault))

        # Pre-generate embeddings
        enable_fake_provider(engine.semantic.generator).batch_embed(sample_memories)

        # Perform hybrid search
        results = engine.search("database production", sample_memories, top_k=3)

        # Should return ranked results
        assert len(results) > 0
        assert all('combined_score' in r for r in results)

    def test_unavailable_semantic_provider_uses_lexical_only(self, temp_vault, sample_memories):
        engine = HybridSearchEngine(str(temp_vault))
        results = engine.search("PostgreSQL database", sample_memories, top_k=5)

        assert results
        assert all(result["semantic_score"] == 0.0 for result in results)
        assert all(result["search_type"] == "lexical" for result in results)

    def test_search_type_identification(self, temp_vault, sample_memories):
        """Test that search type is correctly identified"""
        engine = HybridSearchEngine(str(temp_vault))
        enable_fake_provider(engine.semantic.generator).batch_embed(sample_memories)

        results = engine.search("PostgreSQL", sample_memories, top_k=5)

        # Should have different search types
        types = {r.get('search_type') for r in results}
        assert 'lexical' in types or 'semantic' in types or 'both' in types

    def test_search_quality_analysis(self, temp_vault, sample_memories):
        """Test search quality analysis"""
        engine = HybridSearchEngine(str(temp_vault))
        enable_fake_provider(engine.semantic.generator).batch_embed(sample_memories)

        results = engine.search("API design", sample_memories, top_k=3)
        quality = engine.get_search_quality(results)

        # Should have quality metrics
        assert 'quality' in quality
        assert 'balance' in quality
        assert quality['total_results'] > 0


class TestMLRanker:
    """Test ML-based ranking"""

    def test_historical_name_is_a_compatibility_alias_for_truthful_ranker(self):
        assert ml_ranker.MLRanker is ml_ranker.HeuristicRanker
        assert ml_ranker.MLRanker.__name__ == "HeuristicRanker"

    def test_ranker_weights_sum_to_one(self):
        """Test that weights sum to 1.0"""
        ranker = MLRanker()

        total = sum(ranker.weights.values())
        assert abs(total - 1.0) < 0.001

    def test_recency_scoring(self):
        """Test recency decay function"""
        ranker = MLRanker()

        # Create memories with different ages
        now = datetime.now()
        memory_today = {"timestamp": now.isoformat()}
        memory_30d = {"timestamp": (now - timedelta(days=30)).isoformat()}
        memory_100d = {"timestamp": (now - timedelta(days=100)).isoformat()}

        score_today = ranker._recency_score(memory_today)
        score_30d = ranker._recency_score(memory_30d)
        score_100d = ranker._recency_score(memory_100d)

        # Should decay over time
        assert score_today > score_30d > score_100d
        assert 0.0 <= score_today <= 1.0

    def test_match_type_scoring(self):
        """Test match type scoring"""
        ranker = MLRanker()

        candidate_exact = {'content': 'PostgreSQL database'}
        candidate_partial = {'content': 'Use PostgreSQL for production'}
        candidate_fuzzy = {'content': 'Select RDBMS like PostgreSQL'}

        score_exact = ranker._match_type_score("postgresql", candidate_exact)
        score_partial = ranker._match_type_score("postgresql", candidate_partial)
        score_fuzzy = ranker._match_type_score("postgres", candidate_fuzzy)

        # Exact > partial > fuzzy
        assert score_exact >= score_partial >= 0.5

    def test_feature_extraction(self, sample_memories):
        """Test feature extraction for ranking"""
        ranker = MLRanker()

        candidate = {
            'memory_id': sample_memories[0]['memory_id'],
            'content': 'PostgreSQL database',
            'combined_score': 0.85
        }

        features = ranker._extract_features("database", candidate, sample_memories)

        # Should have all features
        assert 'search_relevance' in features
        assert 'memory_quality' in features
        assert 'recency' in features
        assert 'novelty' in features
        assert 'match_type' in features

    def test_ranking_with_multiple_candidates(self, temp_vault, sample_memories):
        """Test ranking multiple candidates"""
        ranker = MLRanker()

        candidates = [
            {
                'memory_id': m['memory_id'],
                'content': m['content'],
                'combined_score': 0.5 + i * 0.1
            }
            for i, m in enumerate(sample_memories[:3])
        ]

        ranked = ranker.rank("test", candidates, sample_memories)

        # Should return all candidates
        assert len(ranked) == len(candidates)

        # Should have ML scores
        assert all('ml_score' in r for r in ranked)

        # Should be sorted by score (descending)
        scores = [r['ml_score'] for r in ranked]
        assert scores == sorted(scores, reverse=True)

    def test_weight_modification(self):
        """Test modifying ranking weights"""
        ranker = MLRanker()

        new_weights = {
            'search_relevance': 0.5,
            'memory_quality': 0.3,
            'recency': 0.1,
            'novelty': 0.05,
            'match_type': 0.05
        }

        ranker.set_weights(new_weights)

        assert ranker.get_weights() == new_weights

    def test_invalid_weights_rejected(self):
        """Test that invalid weights are rejected"""
        ranker = MLRanker()

        # Weights that don't sum to 1.0
        invalid_weights = {
            'search_relevance': 0.5,
            'memory_quality': 0.3,
            'recency': 0.1,
            'novelty': 0.05,
            'match_type': 0.04  # Sum = 0.99
        }

        with pytest.raises(ValueError):
            ranker.set_weights(invalid_weights)


class TestPhase7Integration:
    """Integration tests for Phase 7"""

    def test_full_semantic_pipeline(self, temp_vault, sample_memories):
        """Test complete semantic search pipeline"""
        # Generate embeddings
        gen = enable_fake_provider(EmbeddingGenerator(str(temp_vault)))
        embeddings = gen.batch_embed(sample_memories)
        gen.save()

        # Semantic search
        engine = SemanticSearchEngine(str(temp_vault))
        enable_fake_provider(engine.generator)
        sem_results = engine.search("database", sample_memories, top_k=3)

        # Should get results
        assert len(sem_results) > 0

    def test_full_hybrid_pipeline(self, temp_vault, sample_memories):
        """Test complete hybrid search pipeline"""
        hybrid = HybridSearchEngine(str(temp_vault))
        enable_fake_provider(hybrid.semantic.generator).batch_embed(sample_memories)

        results = hybrid.search("PostgreSQL API design", sample_memories, top_k=3)

        assert len(results) > 0
        assert all('combined_score' in r for r in results)

    def test_hybrid_plus_ml_ranking(self, temp_vault, sample_memories):
        """Test hybrid search + ML ranking"""
        hybrid = HybridSearchEngine(str(temp_vault))
        enable_fake_provider(hybrid.semantic.generator).batch_embed(sample_memories)

        hybrid_results = hybrid.search("database", sample_memories, top_k=5)

        # Rank with ML
        ranker = MLRanker()
        ranked = ranker.rank("database", hybrid_results, sample_memories)

        assert len(ranked) > 0
        assert all('ml_score' in r for r in ranked)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
