"""IG-03 benchmark isolation and provider result tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from evals.ig03.benchmark import benchmark_providers, load_extraction_cases
from brain_eleven.extraction.semantic import UnavailableProvider


def test_benchmark_loads_only_public_dev_or_validation():
    cases = load_extraction_cases(split="dev")
    assert cases
    assert all(case["split"] == "dev" for case in cases)
    with pytest.raises(ValueError):
        load_extraction_cases(split="holdout")


def test_benchmark_report_is_content_free_and_marks_unavailable_provider():
    report = benchmark_providers(
        split="validation",
        providers={"local": UnavailableProvider("local-qwen", "test", "not_installed")},
        git_sha="a" * 40,
    )
    rendered = json.dumps(report, ensure_ascii=False).lower()
    assert report["source"]["holdout_included"] is False
    assert report["providers"]["local"]["status_counts"]["SEMANTIC_UNAVAILABLE"]
    assert "sqlite kullanacağız" not in rendered
    assert "prompt" not in rendered
    assert "transcript" not in rendered


def test_benchmark_requires_revision_bound_sha():
    with pytest.raises(ValueError):
        benchmark_providers(split="dev", providers={}, git_sha="bogus")
