"""Security-relevant configuration checks for the ML ranker."""

import pytest

from brain_eleven.search import ranker as ml_ranker


def test_invalid_weight_configuration_raises_in_optimized_and_normal_runs():
    ranker = ml_ranker.MLRanker()
    ranker.weights["search_relevance"] = 0.0

    with pytest.raises(ValueError, match="Weights must sum to 1.0"):
        ranker._validate_weights()
