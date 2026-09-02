"""Security-relevant configuration checks for the ML ranker."""

import importlib.util
from pathlib import Path

import pytest


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
SPEC = importlib.util.spec_from_file_location("ml_ranker", SCRIPTS / "ml-ranker.py")
ml_ranker = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ml_ranker)


def test_invalid_weight_configuration_raises_in_optimized_and_normal_runs():
    ranker = ml_ranker.MLRanker()
    ranker.weights["search_relevance"] = 0.0

    with pytest.raises(ValueError, match="Weights must sum to 1.0"):
        ranker._validate_weights()
