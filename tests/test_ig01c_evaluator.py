"""IG01-C evaluator tests: formulas, anti-gaming controls and hard gates."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from evals.ig01c import (
    EvaluationContractError,
    evaluate_case,
    evaluate_corpus,
    evaluate_extraction_case,
    evaluate_lifecycle_case,
    evaluate_reference_case,
    evaluate_retrieval_case,
    f1_score,
    mandatory_recall,
    mean_reciprocal_rank,
    noise_ratio,
    precision_at_k,
    recall_at_k,
    token_waste,
    validate_report,
)


def retrieval_case(**overrides):
    value = {
        "case_id": "retrieval-1",
        "family": "retrieval",
        "case_kind": "answerable",
        "project_id": "project-a",
        "candidate_ids": ["required", "acceptable", "foreign", "old", "resolved"],
        "required_ids": ["required"],
        "acceptable_ids": ["acceptable"],
        "mandatory_ids": ["required"],
        "forbidden_ids": ["foreign", "old", "resolved"],
        "candidate_metadata": [
            {"id": "required", "project_id": "project-a", "status": "active", "token_count": 10},
            {"id": "acceptable", "project_id": "project-a", "status": "active", "token_count": 10},
            {"id": "foreign", "project_id": "project-b", "status": "active", "token_count": 10},
            {"id": "old", "project_id": "project-a", "status": "superseded", "token_count": 10},
            {"id": "resolved", "project_id": "project-a", "status": "resolved", "token_count": 10},
        ],
    }
    value.update(overrides)
    return value


def extraction_case(**overrides):
    value = {
        "case_id": "extraction-1",
        "family": "extraction",
        "case_kind": "answerable",
        "expected": {
            "commitment": "explicit",
            "memory_type": "decision",
            "state_operation": "ADD",
            "correction": False,
            "target_behavior": "none",
            "scope": "project-local",
            "source_role": "user",
        },
    }
    value.update(overrides)
    return value


def test_primitive_retrieval_metrics_are_explicit_and_anti_gaming():
    precision = precision_at_k(["a", "b", "noise"], {"a", "b"}, 3)
    recall = recall_at_k(["a", "b", "noise"], {"a", "b"}, 3)
    assert precision.value == pytest.approx(2 / 3)
    assert recall.value == 1.0
    assert f1_score(precision, recall).value == pytest.approx(0.8)
    assert mean_reciprocal_rank(["noise", "b"], {"a", "b"}).value == pytest.approx(0.5)
    assert mandatory_recall(["a"], ["a", "b"]).value == 0.5
    assert noise_ratio(["a", "noise"], ["a"]).value == 0.5
    assert token_waste(["a", "noise"], ["a"], {"a": 10, "noise": 20}).value == pytest.approx(2 / 3)

    select_none = precision_at_k([], {"a"}, 0)
    select_all = precision_at_k(["a", "noise"], {"a"}, 2)
    assert select_none.value == 0.0 and select_none.empty_selection is True
    assert select_all.value == 0.5
    assert recall_at_k([], [], 5).not_applicable is True


def test_retrieval_case_uses_fixture_metadata_for_all_scope_lifecycle_gates():
    result = evaluate_retrieval_case(
        retrieval_case(),
        ["required", "foreign", "old", "resolved"],
        k=4,
    )
    assert result["metrics"]["precision_at_k"]["value"] == pytest.approx(0.25)
    assert set(result["violations"]) == {
        "wrong_project_leakage",
        "forbidden_leakage",
        "superseded_leakage",
        "resolved_leakage",
    }
    assert result["passed"] is False


def test_extraction_accepts_exact_user_decision_and_rejects_false_commitment():
    expected = extraction_case()["expected"]
    good = evaluate_extraction_case(extraction_case(), expected)
    assert good["metrics"]["decision_precision"]["value"] == 1.0
    assert good["metrics"]["decision_recall"]["value"] == 1.0
    assert good["safety_events"] == []

    false = evaluate_extraction_case(
        extraction_case(
            expected={
                **expected,
                "commitment": "none",
                "memory_type": "no_commitment",
                "state_operation": "NOOP",
            }
        ),
        expected,
    )
    assert "false_commitment" in false["violations"]
    assert any(event["review_required"] for event in false["safety_events"])


def test_extraction_assistant_proposal_and_direct_canonical_write_are_gates():
    case = extraction_case(
        expected={
            "commitment": "none",
            "memory_type": "decision",
            "state_operation": "NOOP",
            "correction": False,
            "target_behavior": "none",
            "scope": "project-local",
            "source_role": "assistant",
        }
    )
    result = evaluate_extraction_case(
        case,
        {
            "commitment": "explicit",
            "memory_type": "decision",
            "state_operation": "ADD",
            "correction": False,
            "scope": "project-local",
            "source_role": "user",
            "canonical_commit": True,
            "confidence": 0.9,
        },
    )
    assert "assistant_as_user_commitment" in result["violations"]
    assert "forbidden_leakage" in result["violations"]


def test_reference_resolution_abstains_on_ambiguous_target_and_blocks_foreign_target():
    ambiguous = {
        "case_id": "reference-ambiguous",
        "family": "reference_resolution",
        "expected": {"abstain": True},
        "labels": {"primary": {"abstain": True}},
        "project_id": "project-a",
    }
    safe = evaluate_reference_case(ambiguous, {"status": "AMBIGUOUS", "candidate_targets": ["a", "b"]})
    assert safe["metrics"]["ambiguous_abstention_rate"]["value"] == 1.0
    assert safe["violations"] == []

    unsafe = evaluate_reference_case(
        {
            **ambiguous,
            "expected": {"target_id": "a", "status": "RESOLVED_TARGET"},
            "labels": {"primary": {"abstain": False}},
        },
        {"status": "RESOLVED_TARGET", "target_id": "b", "target_project_id": "project-b", "operation": "SUPERSEDE"},
    )
    assert "cross_project_target" in unsafe["violations"]
    assert "false_supersession" in unsafe["violations"]


def test_lifecycle_cycle_and_invalid_transition_are_visible():
    cycle = evaluate_lifecycle_case(
        {
            "case_id": "lifecycle-1",
            "family": "lifecycle",
            "expected": {"operation": "RESOLVE"},
        },
        {"operation": "RESOLVE", "from_status": "active", "to_status": "resolved", "history": ["active", "resolved", "active"]},
    )
    assert "lifecycle_cycle" in cycle["violations"]
    assert cycle["metrics"]["lifecycle_transition_safety"]["value"] == 0.0


def test_corpus_runner_is_strict_and_reports_select_all_controls_without_content():
    cases = [retrieval_case(case_id="a"), extraction_case(case_id="b")]
    outputs = {
        "a": {"retrieved_ids": ["required", "acceptable"]},
        "b": extraction_case()["expected"],
    }
    report = evaluate_corpus(
        cases,
        outputs,
        corpus_version="ig-eval-v2",
        split="dev",
        retrieval_k=2,
        git_sha="abc123",
    )
    assert report["corpus"]["scored_case_count"] == 2
    assert "a" in report["controls"]
    assert report["controls"]["a"]["select_all"]["metrics"]["noise_ratio"]["value"] >= 0.0
    assert "query" not in report and "content" not in str(report)
    assert set(report["safety_gates"]) == {
        "wrong_project_leakage", "forbidden_leakage", "assistant_as_user_commitment",
        "cross_project_target", "superseded_leakage", "resolved_leakage", "lifecycle_cycle",
        "false_supersession", "false_commitment",
    }
    validate_report(report)

    with pytest.raises(EvaluationContractError, match="outputs do not match"):
        evaluate_corpus(cases, {"a": outputs["a"]}, corpus_version="v", split="dev")


def test_report_rejects_raw_content_and_near_zero_events_without_review():
    case = retrieval_case()
    report = evaluate_corpus(
        [case], {case["case_id"]: {"retrieved_ids": ["required"]}}, corpus_version="v", split="dev"
    )
    tampered = copy.deepcopy(report)
    tampered["cases"][0]["prompt"] = "secret raw prompt"
    with pytest.raises(EvaluationContractError, match="prohibited raw content"):
        validate_report(tampered)

    broken = copy.deepcopy(report)
    broken["safety_gates"]["false_commitment"]["count"] = 1
    broken["safety_gates"]["false_commitment"]["review_records"] = []
    with pytest.raises(EvaluationContractError, match="review records incomplete"):
        validate_report(broken)


def test_current_ig01b_public_corpus_can_be_scored_without_raw_content_output():
    root = Path(__file__).resolve().parents[1] / "evals" / "ig01b" / "public" / "ig-eval-v2"
    cases = [
        json.loads(line)
        for split in ("dev", "validation")
        for line in (root / f"{split}.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    outputs = {}
    for case in cases:
        if case["family"] == "retrieval":
            outputs[case["case_id"]] = {
                "retrieved_ids": list(dict.fromkeys(case["required_ids"] + case["acceptable_ids"]))
            }
        elif case["family"] == "extraction":
            outputs[case["case_id"]] = case["expected"]
        else:
            outputs[case["case_id"]] = {"status": "AMBIGUOUS"}
    report = evaluate_corpus(
        cases,
        outputs,
        corpus_version="ig-eval-v2",
        split="dev-validation",
        retrieval_k=5,
    )
    assert report["corpus"]["case_count"] == 114
    assert report["corpus"]["excluded_case_count"] == 0
    assert all(row["passed"] for row in report["safety_gates"].values())
    assert "query" not in json.dumps(report)
