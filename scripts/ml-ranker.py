#!/usr/bin/env python3
"""
Brain-Eleven ML Ranking Engine
Machine learning-based ranking combining multiple signals

Features ranked:
- Search relevance (lexical + semantic): 40%
- Memory quality (from validator): 20%
- Recency (freshness): 15%
- Novelty (from validator): 15%
- Match type (exact/partial/fuzzy): 10%
"""

import json
import numpy as np
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional


class MLRanker:
    """Machine learning-based ranking engine"""

    def __init__(self):
        # Feature weights (must sum to 1.0)
        self.weights = {
            'search_relevance': 0.40,  # Combined lexical + semantic
            'memory_quality': 0.20,    # Quality score from validator
            'recency': 0.15,           # How recent (freshness decay)
            'novelty': 0.15,           # Novelty from validator
            'match_type': 0.10         # Exact > partial > fuzzy match
        }

        self._validate_weights()

    def _validate_weights(self) -> None:
        """Reject invalid ranking configurations in every runtime mode."""
        total_weight = sum(self.weights.values())
        if not np.isclose(total_weight, 1.0, atol=0.001):
            raise ValueError(f"Weights must sum to 1.0, got {total_weight}")

    # ========================================================================
    # RANKING OPERATIONS
    # ========================================================================

    def rank(
        self,
        query: str,
        candidates: List[Dict],
        memories: List[Dict]
    ) -> List[Dict]:
        """Rank candidates using ML features"""

        ranked = []

        for candidate in candidates:
            # Extract features
            features = self._extract_features(query, candidate, memories)

            # Compute weighted score
            ml_score = self._compute_score(features)

            # Add to result
            candidate_result = dict(candidate)  # Copy to avoid mutation
            candidate_result['ml_score'] = ml_score
            candidate_result['ml_features'] = features

            ranked.append(candidate_result)

        # Sort by score
        ranked.sort(key=lambda x: x['ml_score'], reverse=True)

        return ranked

    # ========================================================================
    # FEATURE EXTRACTION
    # ========================================================================

    def _extract_features(
        self,
        query: str,
        candidate: Dict,
        memories: List[Dict]
    ) -> Dict[str, float]:
        """Extract ML features for ranking"""

        # Find full memory record
        memory = next(
            (m for m in memories if m['memory_id'] == candidate.get('memory_id')),
            None
        )

        # Search relevance (already computed in hybrid search)
        search_relevance = candidate.get('combined_score', 0.0)

        # Memory quality (from validator)
        memory_quality = memory.get('quality_score', 0.5) if memory else 0.5

        # Recency (freshness decay)
        recency = self._recency_score(memory) if memory else 0.5

        # Novelty (from validator)
        novelty = memory.get('novelty', 0.5) if memory else 0.5

        # Match type (exact/partial/fuzzy)
        match_type = self._match_type_score(query, candidate)

        return {
            'search_relevance': search_relevance,
            'memory_quality': memory_quality,
            'recency': recency,
            'novelty': novelty,
            'match_type': match_type
        }

    def _recency_score(self, memory: Dict) -> float:
        """Score based on how recent the memory is"""

        try:
            timestamp_str = memory.get('timestamp')
            if not timestamp_str:
                return 0.5

            # Parse timestamp
            timestamp = datetime.fromisoformat(timestamp_str)

            # Days since creation
            days_old = (datetime.now() - timestamp).days

            # Decay curve: 1.0 today, 0.5 at 30 days, 0.1 at 100 days
            # Using exponential decay: exp(-days_old / 30)
            decay_rate = 30  # Half-life in days
            recency = np.exp(-days_old / decay_rate)

            # Clamp to [0.1, 1.0]
            return max(0.1, min(1.0, recency))

        except Exception as e:
            print(f"⚠️  Failed to compute recency: {e}")
            return 0.5

    def _match_type_score(self, query: str, candidate: Dict) -> float:
        """Score based on match type (exact > partial > fuzzy)"""

        content = candidate.get('content', '').lower()
        query_lower = query.lower()

        # Exact match at start (exact opening)
        if content.startswith(query_lower):
            return 1.0

        # Partial match (word boundary)
        words = query_lower.split()
        all_words_match = all(word in content for word in words)
        if all_words_match:
            return 0.9

        # Substring match (fuzzy)
        if query_lower in content:
            return 0.7

        # No direct match (but still ranked by semantic similarity)
        return 0.5

    # ========================================================================
    # SCORING
    # ========================================================================

    def _compute_score(self, features: Dict[str, float]) -> float:
        """Weighted combination of features"""

        score = 0.0

        for feature_name, weight in self.weights.items():
            feature_value = features.get(feature_name, 0.0)

            # Ensure value is in [0, 1]
            feature_value = max(0.0, min(1.0, feature_value))

            score += feature_value * weight

        return score

    # ========================================================================
    # RANKING ANALYSIS
    # ========================================================================

    def get_ranking_analysis(self, ranked_results: List[Dict]) -> Dict:
        """Analyze ranking quality"""

        if not ranked_results:
            return {"total": 0, "quality": 0}

        # Scores
        scores = [r.get('ml_score', 0) for r in ranked_results]

        # Feature analysis
        all_features = {}
        for result in ranked_results:
            features = result.get('ml_features', {})
            for feature, value in features.items():
                if feature not in all_features:
                    all_features[feature] = []
                all_features[feature].append(value)

        feature_stats = {}
        for feature, values in all_features.items():
            feature_stats[feature] = {
                'mean': np.mean(values),
                'max': np.max(values),
                'min': np.min(values)
            }

        return {
            "total_results": len(ranked_results),
            "avg_score": np.mean(scores),
            "max_score": np.max(scores),
            "min_score": np.min(scores),
            "feature_stats": feature_stats,
            "weights": self.weights
        }

    # ========================================================================
    # PARAMETER TUNING
    # ========================================================================

    def set_weights(self, weights: Dict[str, float]):
        """Update ranking weights"""

        # Validate
        total = sum(weights.values())
        if abs(total - 1.0) > 0.001:
            raise ValueError(f"Weights must sum to 1.0, got {total}")

        self.weights = weights
        print(f"✅ Updated ranking weights:")
        for name, weight in weights.items():
            print(f"   {name}: {weight:.2%}")

    def get_weights(self) -> Dict[str, float]:
        """Get current ranking weights"""
        return dict(self.weights)


# ============================================================================
# CLI & DEMO
# ============================================================================

if __name__ == "__main__":
    vault_path = Path.home() / "Documents/Brain-Eleven"

    # Load memories
    validated_file = vault_path / ".claude/validated-memory.json"
    if not validated_file.exists():
        print("❌ No validated memories found")
        import sys
        sys.exit(1)

    with open(validated_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
        memories = data.get("validated_memory", [])

    print(f"📚 Loaded {len(memories)} memories")

    # Initialize ranker
    ranker = MLRanker()

    print(f"\n⚙️  Ranking Configuration:")
    print(f"   Default weights:")
    for feature, weight in ranker.get_weights().items():
        print(f"     {feature}: {weight:.0%}")

    # Demo: Create sample candidates (as if from hybrid search)
    demo_candidates = [
        {
            'memory_id': memories[0]['memory_id'],
            'content': memories[0]['content'][:60],
            'combined_score': 0.85,
            'lexical_score': 0.90,
            'semantic_score': 0.82
        },
        {
            'memory_id': memories[1]['memory_id'] if len(memories) > 1 else memories[0]['memory_id'],
            'content': memories[1]['content'][:60] if len(memories) > 1 else memories[0]['content'][:60],
            'combined_score': 0.72,
            'lexical_score': 0.65,
            'semantic_score': 0.75
        }
    ]

    print(f"\n🔍 Demo ranking {len(demo_candidates)} candidates...\n")

    # Rank candidates
    ranked = ranker.rank("test query", demo_candidates, memories)

    print(f"Ranked results:")
    for i, result in enumerate(ranked, 1):
        score = result.get('ml_score', 0)
        features = result.get('ml_features', {})

        print(f"\n  {i}. Score: {score:.3f}")
        print(f"     Content: {result['content']}...")
        print(f"     Features:")
        for fname, fvalue in features.items():
            weight = ranker.weights[fname]
            contribution = fvalue * weight
            print(f"       {fname}: {fvalue:.3f} (× {weight:.0%} = {contribution:.3f})")

    # Analysis
    print(f"\n📊 Ranking Analysis:")
    analysis = ranker.get_ranking_analysis(ranked)
    print(f"   Results: {analysis['total_results']}")
    print(f"   Avg Score: {analysis['avg_score']:.3f}")
    print(f"   Max Score: {analysis['max_score']:.3f}")
    print(f"   Min Score: {analysis['min_score']:.3f}")

    print(f"\n✅ ML ranking demo complete")
