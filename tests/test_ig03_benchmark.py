"""IG-03 benchmark isolation and provider result tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from evals.ig03.benchmark import benchmark_providers, load_extraction_cases, _run_provider
from brain_eleven.extraction.semantic import (
    ProviderResult,
    SEMANTIC_SCHEMA_VERSION,
    SemanticProposition,
    SemanticStatus,
    UnavailableProvider,
)


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
        git_sha=None,
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
    with pytest.raises(ValueError, match="exact repository HEAD"):
        benchmark_providers(split="dev", providers={}, git_sha="a" * 40)


def test_benchmark_rejects_historical_corpus_instead_of_mislabeling_it():
    with pytest.raises(ValueError, match="current frozen corpus"):
        load_extraction_cases(split="dev", corpus_root=Path("evals/ig01b/public/ig-eval-v1"))


def test_unavailable_provider_metrics_are_not_applicable():
    result = _run_provider(
        UnavailableProvider("local-qwen", "test", "not_installed"),
        load_extraction_cases(split="dev"),
    )
    assert result["measurement"]["applicable_case_count"] == 0
    assert all(value["not_applicable"] for value in result["metrics"].values())


def test_provider_provenance_is_revision_bound():
    result = benchmark_providers(
        split="dev",
        providers={"local": UnavailableProvider("local-qwen", "test", "not_installed")},
        git_sha=None,
    )
    provenance = result["providers"]["local"]["provider"]["provenance"]
    assert provenance[0]["schema_version"] == "ig01-a-proposition-v1"
    assert provenance[0]["provider_revision"] == "unavailable-provider-v1"
    assert provenance[0]["availability_code"] == "not_installed"


def test_benchmark_ece_uses_ig01c_ten_bin_batch_aggregation():
    cases = [
        {
            "case_id": "ece-correct",
            "conversation": [{"role": "user", "text": "decision"}],
            "project_id": "project-alpha",
            "expected": {
                "commitment": "explicit", "memory_type": "decision", "state_operation": "ADD",
                "correction": False, "target_behavior": "none", "scope": "project-local", "source_role": "user",
            },
        },
        {
            "case_id": "ece-wrong",
            "conversation": [{"role": "user", "text": "other"}],
            "project_id": "project-alpha",
            "expected": {
                "commitment": "explicit", "memory_type": "decision", "state_operation": "ADD",
                "correction": False, "target_behavior": "none", "scope": "project-local", "source_role": "user",
            },
        },
    ]

    class Provider:
        provider_id = "ece-test"
        model = "test"
        provider_revision = "ece-test-v1"

        def __init__(self):
            self.calls = 0

        def extract(self, message, *, project_id=None, schema_version=SEMANTIC_SCHEMA_VERSION):
            self.calls += 1
            proposition = SemanticProposition(
                candidate_id=f"candidate-{self.calls}", project_id="project-alpha", claim_type="decision",
                subject="decision", predicate="asserts", value="decision", commitment="explicit",
                temporal_scope=None, source_role="user", evidence_refs=(f"evidence-{self.calls}",),
                confidence_components={"model": 0.1}, correction_clues=None, target_clues=None,
            )
            if self.calls == 2:
                proposition = SemanticProposition(
                    **{**proposition.to_dict(), "claim_type": "observation", "evidence_refs": [f"evidence-{self.calls}"]}
                )
            return ProviderResult(
                status=SemanticStatus.MEASURED.value, provider_id=self.provider_id, model=self.model,
                propositions=(proposition,), metadata={
                    "requested_schema_version": schema_version, "project_bound": True,
                    "provider_revision": self.provider_revision, "availability_code": "available",
                },
            )

    result = _run_provider(Provider(), cases)
    assert result["metrics"]["ece"]["value"] == pytest.approx(0.4)
