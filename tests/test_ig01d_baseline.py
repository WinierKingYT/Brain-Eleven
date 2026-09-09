"""Contract tests for the production-independent IG01-D baseline adapter."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import pytest

from evals.ig01d.contracts import BaselineContractError, validate_baseline_report, validate_pair_report
from evals.ig01d.fingerprint import corpus_split_fingerprint
from evals.ig01d.spike import run_feasibility_probe


ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "evals" / "corpus-v2"
_INVARIANT_NAMES = ("forbidden_context", "resolved_lifecycle_leakage", "superseded_lifecycle_leakage", "wrong_project_leakage")
_INVARIANT_EVIDENCE = {
    name: {"state": "pass", "failed_case_ids": [], "unsupported_case_ids": [], "not_applicable_case_ids": []}
    for name in _INVARIANT_NAMES
}
_CASE_INVARIANTS = {name: "pass" for name in _INVARIANT_NAMES}


def _provider_report(provider_id: str = "context_compiler_baseline_v1") -> dict:
    task_id = "p15_v2_basic_relevance_001"
    return {
        "schema_version": 1,
        "report_type": "brain_eleven_ig01d_baseline",
        "evaluator_version": "ig01c-1.0.0",
        "provider": {"id": provider_id, "role": "v1", "capabilities": {"selection": "existing_provider_adapter", "production_mutation": False}},
        "corpus": {
            "corpus_version": "phase15-corpus-v2",
            "fixture_id": "phase15_contract",
            "suite": "public",
            "split": ["dev", "test"],
            "task_count": 1,
            "task_ids": [task_id],
            "split_fingerprint": "sha256:" + "a" * 64,
        },
        "source": {
            "git_sha": "a" * 40,
            "corpus_version": "phase15-corpus-v2",
            "evaluator_version": "ig01c-1.0.0",
            "evaluation_source_fingerprint": "sha256:" + "b" * 64,
            "seed": 17,
            "noise_count": 24,
        },
        "metrics": {
            "case_count": 1,
            "context_precision": 0.5,
            "context_recall": 0.5,
            "selected_items": 1,
            "relevant_selected_items": 1,
            "required_items": 2,
            "required_selected_items": 1,
            "wrong_project_leakage_rate": 0.0,
            "forbidden_context_rate": 0.0,
            "superseded_leakage_rate": 0.0,
            "resolved_leakage_rate": 0.0,
            "unlabeled_context_rate": 0.0,
        },
        "invariants": deepcopy(_INVARIANT_EVIDENCE),
        "measurement": {
            "elapsed_ms": 1.0,
            "case_count": 1,
            "per_case_mean_ms": 1.0,
            "p50_ms": None,
            "p95_ms": None,
            "budget_measurement": "token counts unavailable in normalized provider contract",
        },
        "cases": [{
            "task_id": task_id,
            "project_id": "promtgen",
            "expected": {"required": ["mem_promtgen_storage"], "useful": [], "forbidden": []},
            "selected_ids": ["mem_promtgen_storage"],
            "missing_required_ids": [],
            "unexpected_selected_ids": [],
            "forbidden_selected_ids": [],
            "metrics": {
                "task_id": task_id,
                "selected_count": 1,
                "relevant_selected_count": 1,
                "required_count": 1,
                "required_selected_count": 1,
                "useful_selected_count": 0,
                "context_precision": 1.0,
                "context_recall": 1.0,
                "wrong_project_selected_count": 0,
                "wrong_project_leakage_count": 0,
                "forbidden_context_count": 0,
                "superseded_selected_count": 0,
                "superseded_leakage_count": 0,
                "resolved_selected_count": 0,
                "resolved_leakage_count": 0,
                "unlabeled_selection_count": 0,
            },
            "invariants": dict(_CASE_INVARIANTS),
            "violations": [],
            "passed": True,
        }],
    }


def _pair_report() -> dict:
    v1 = _provider_report()
    v2 = _provider_report("context_compiler_v2")
    v2["provider"]["role"] = "v2"
    return {
        "schema_version": 1,
        "report_type": "brain_eleven_ig01d_pair",
        "evaluator_version": "ig01c-1.0.0",
        "corpus": {
            "corpus_version": "phase15-corpus-v2",
            "fixture_id": "phase15_contract",
            "suite": "public",
            "split": ["dev", "test"],
            "task_count": 1,
            "task_ids": ["p15_v2_basic_relevance_001"],
            "split_fingerprint": "sha256:" + "a" * 64,
        },
        "source": v1["source"],
        "providers": {"v1": v1, "v2": v2},
        "comparison": {
            "schema_version": 1,
            "comparison_type": "brain_eleven_evaluation_regression",
            "baseline": {"provider_id": v1["provider"]["id"]},
            "candidate": {"provider_id": v2["provider"]["id"]},
            "corpus": {"fixture_id": "phase15_contract", "suite": "public", "task_count": 1},
            "metric_deltas": {
                "context_precision": {"baseline": 0.5, "candidate": 0.5, "delta": 0.0},
                "context_recall": {"baseline": 0.5, "candidate": 0.5, "delta": 0.0},
            },
            "invariant_changes": {
                name: {"new_failed_case_ids": [], "resolved_failed_case_ids": [], "new_unsupported_case_ids": [], "resolved_unsupported_case_ids": []}
                for name in _INVARIANT_NAMES
            },
            "candidate_gate": {"passed": True, "failed_invariants": {}, "unsupported_invariants": {}},
            "outcome": "unchanged",
        },
        "measurement": {"v1_elapsed_ms": 1.0, "v2_elapsed_ms": 1.0, "budget_measurement": "token counts unavailable in normalized provider contract"},
        "feasibility": {
            "status": "SEMANTIC_UNAVAILABLE",
            "provider_id": "none",
            "reason": "no real embedding or cross-encoder provider is installed",
            "case_count": 50,
            "split": "dev",
            "holdout_included": False,
            "corpus_split_fingerprint": "sha256:" + "a" * 64,
            "precision": None,
            "empirical_ceiling": None,
            "elapsed_ms": 1.0,
            "measurement": "no score without a real embedding plus cross-encoder pair",
        },
        "target_derivation": {
            "formula": "max(program_floor + margin, baseline + realistic_gain)",
            "margin": 0.05,
            "realistic_gain": 0.10,
            "program_floor": {"context_precision": 0.60, "mandatory_recall": 0.80, "mrr": 0.85},
            "targets": {
                "context_precision": {"value": 0.65, "status": "PROVISIONAL_SPIKE_UNAVAILABLE", "baseline": 0.5},
                "mandatory_recall": {"value": 0.85, "status": "PROVISIONAL_SPIKE_UNAVAILABLE", "baseline": 0.5},
                "mrr": {"value": 0.85, "status": "METRIC_UNAVAILABLE_IN_NORMALIZED_PROVIDER_CONTRACT", "baseline": None},
            },
            "quality_visibility": {"v2_must_exceed_v1": True, "promotion_allowed": False, "spike_status": "SEMANTIC_UNAVAILABLE"},
        },
    }


def test_pair_report_accepts_same_inputs():
    assert validate_pair_report(_pair_report())["report_type"] == "brain_eleven_ig01d_pair"


def test_pair_report_rejects_provider_task_mismatch():
    report = _pair_report()
    report["providers"]["v2"]["corpus"]["task_ids"] = ["p15_v2_basic_relevance_002"]
    with pytest.raises(BaselineContractError):
        validate_pair_report(report)


def test_pair_report_rejects_provider_source_fingerprint_mismatch():
    report = _pair_report()
    report["providers"]["v2"]["source"]["evaluation_source_fingerprint"] = "sha256:" + "c" * 64
    with pytest.raises(BaselineContractError, match="source.evaluation_source_fingerprint"):
        validate_pair_report(report)


def test_report_rejects_unknown_fields_even_without_sensitive_key_name():
    report = _provider_report()
    report["notes"] = "raw transcript"
    with pytest.raises(BaselineContractError, match="unknown fields"):
        validate_baseline_report(report)
    nested = _provider_report()
    nested["cases"][0]["expected"]["notes"] = "raw transcript"
    with pytest.raises(BaselineContractError, match="unknown fields"):
        validate_baseline_report(nested)


def test_report_rejects_mutating_capability():
    report = _provider_report()
    report["provider"]["capabilities"]["production_mutation"] = True
    with pytest.raises(BaselineContractError, match="read-only"):
        validate_baseline_report(report)


def test_pair_report_rejects_invalid_feasibility_count():
    report = _pair_report()
    report["feasibility"]["case_count"] = 1
    with pytest.raises(BaselineContractError, match="50 DEV"):
        validate_pair_report(report)


def test_pair_report_rejects_measured_feasibility_without_scores():
    report = _pair_report()
    report["feasibility"].update(
        {
            "status": "MEASURED",
            "provider_id": "sentence_transformers",
            "reason": "real embedding plus cross-encoder pair measured",
            "measurement": "precision measured on 50 DEV cases",
        }
    )
    with pytest.raises(BaselineContractError, match="must include precision and empirical ceiling"):
        validate_pair_report(report)


def test_pair_report_rejects_free_text_in_content_free_fields():
    report = _pair_report()
    report["measurement"]["budget_measurement"] = "prompt: private transcript"
    with pytest.raises(BaselineContractError, match="bounded code"):
        validate_pair_report(report)
    report = _pair_report()
    report["feasibility"]["reason"] = "secret=private prompt"
    with pytest.raises(BaselineContractError, match="bounded code"):
        validate_pair_report(report)
    report = _pair_report()
    report["providers"]["v1"]["cases"][0]["violations"] = ["raw transcript text"]
    with pytest.raises(BaselineContractError, match="invariant codes"):
        validate_pair_report(report)


def test_pair_report_requires_complete_safety_and_comparison_evidence():
    report = _pair_report()
    del report["providers"]["v1"]["metrics"]["wrong_project_leakage_rate"]
    with pytest.raises(BaselineContractError, match="complete frozen metric set"):
        validate_pair_report(report)
    report = _pair_report()
    del report["providers"]["v1"]["invariants"]["wrong_project_leakage"]
    with pytest.raises(BaselineContractError, match="every safety invariant"):
        validate_pair_report(report)
    report = _pair_report()
    del report["comparison"]["metric_deltas"]["context_recall"]
    with pytest.raises(BaselineContractError, match="complete quality metric set"):
        validate_pair_report(report)
    report = _pair_report()
    del report["comparison"]["invariant_changes"]["wrong_project_leakage"]
    with pytest.raises(BaselineContractError, match="every safety invariant"):
        validate_pair_report(report)


def test_pair_report_rejects_tampered_target_value():
    report = _pair_report()
    report["target_derivation"]["targets"]["context_precision"]["value"] = 0.99
    with pytest.raises(BaselineContractError, match="target"):
        validate_pair_report(report)


def test_pair_report_rejects_task_count_tampering():
    report = _pair_report()
    report["corpus"]["task_count"] = 999
    with pytest.raises(BaselineContractError, match="task_count"):
        validate_pair_report(report)


def test_target_baseline_uses_mandatory_recall_not_context_recall():
    report = _pair_report()
    report["providers"]["v1"]["metrics"]["context_recall"] = 0.25
    assert validate_pair_report(report)["report_type"] == "brain_eleven_ig01d_pair"
    report["target_derivation"]["targets"]["mandatory_recall"]["baseline"] = 0.25
    with pytest.raises(BaselineContractError, match="mandatory_recall"):
        validate_pair_report(report)


def test_baseline_report_rejects_holdout_split():
    report = _provider_report()
    report["corpus"]["split"] = ["dev", "test", "holdout"]
    with pytest.raises(BaselineContractError):
        validate_baseline_report(report)


def test_report_rejects_raw_content_key_recursively():
    report = _provider_report()
    report["cases"][0]["raw_prompt"] = "must never be persisted"
    with pytest.raises(BaselineContractError, match="content-free"):
        validate_baseline_report(report)


def test_public_fingerprint_does_not_read_holdout(tmp_path):
    source = CORPUS
    target = tmp_path / "corpus"
    target.mkdir()
    for relative in (Path("manifest.json"), Path("dev/p15_case.json"), Path("test/p15_case.json"), Path("holdout/p15_case.json")):
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        if relative == Path("manifest.json"):
            destination.write_text("{}\n", encoding="utf-8")
        else:
            destination.write_text(relative.as_posix(), encoding="utf-8")
    before = corpus_split_fingerprint(target)
    (target / "dev/extra.json").write_text("extra", encoding="utf-8")
    after_extra = corpus_split_fingerprint(target)
    assert after_extra != before
    (target / "holdout/p15_case.json").write_text("changed holdout", encoding="utf-8")
    assert corpus_split_fingerprint(target) == after_extra
    assert source.exists()


def test_spike_is_dev_only_and_content_free():
    result = run_feasibility_probe(
        root=ROOT,
        corpus_root=CORPUS,
        fixture_path=ROOT / "evals/fixtures/phase15-contract.json",
        git_sha="a" * 40,
    )
    assert result["case_count"] == 50
    assert result["split"] == "dev"
    assert result["holdout_included"] is False
    assert result["status"] in {"SEMANTIC_UNAVAILABLE", "MEASURED"}
    assert "content" not in json.dumps(result).lower()
