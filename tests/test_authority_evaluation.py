"""Regression coverage for the public and holdout Phase 18 evaluator."""

from __future__ import annotations

from evals.authority.corpus import expectations, load_sidecar, validate_corpus
from evals.authority.schema import AuthorityCorpusError, parse_expectation
from evals.authority_evaluation import run_authority_evaluation


def test_authority_corpus_has_150_public_and_30_holdout_cases():
    assert validate_corpus() == {"public": 150, "holdout": 30, "total": 180}
    assert load_sidecar()["privacy"] == "synthetic_only"
    assert len(expectations("public")) == 150
    assert len(expectations("holdout")) == 30
    assert len(expectations("smoke")) == 8


def test_authority_corpus_schema_rejects_unknown_or_incomplete_expectations():
    document = {
        "schema_version": 1,
        "case_id": "authority_public_bad_001",
        "suite": "public",
        "category": "not-a-category",
        "expected_statuses": {"candidate": "AUTHORITATIVE"},
    }
    try:
        parse_expectation(document)
    except AuthorityCorpusError:
        pass
    else:
        raise AssertionError("invalid authority expectation was accepted")


def test_authority_smoke_evaluation_is_content_safe_and_green():
    report = run_authority_evaluation(suite="smoke")

    assert report["case_count"] == 8
    assert report["expectations_passed"] == 8
    assert all(value["state"] == "pass" for value in report["invariants"].values())
    assert all("canonical decision" not in str(case) for case in report["cases"])
