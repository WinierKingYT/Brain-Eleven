"""Contract tests for the evaluation-only W-06C0 boundary."""

import json
from types import SimpleNamespace

import pytest

from evals.w06c0.evaluation import (
    IMPLEMENTATION_SCOPE_END_REVISION,
    K_VALUES,
    W06C0Error,
    _answerability,
    _metric_rows,
    _safety,
    _select_ids,
    load_corpus,
    run_matrix,
    verify_scope_diff,
    verify_manifest,
)


def test_v3_manifest_and_split_identity_are_frozen():
    manifest = verify_manifest()
    assert manifest["suite_counts"] == {"dev": 70, "test": 60, "holdout": 30}
    for split in ("dev", "test", "holdout"):
        documents, tasks, loaded = load_corpus(split)
        assert len(documents) == len(tasks) == manifest["suite_counts"][split]
        assert loaded["manifest_sha256"] == manifest["manifest_sha256"]
        assert all(len(document["answerability"]["reviewers"]) == 2 for document in documents)


def test_answerability_exclusion_is_explicit_and_deterministic():
    dev_documents, _, _ = load_corpus("dev")
    test_documents, _, _ = load_corpus("test")
    assert sum(document["answerability"]["status"] == "answerable" for document in dev_documents) == 1
    assert all(document["answerability"]["status"] == "unanswerable" for document in test_documents)
    assert all(
        document["answerability"]["reason"] in {
            "query_lacks_target_discriminator",
            "gold_label_depends_on_hidden_fixture_metadata",
        }
        for document in dev_documents + test_documents
        if document["answerability"]["status"] != "answerable"
    )


def test_metric_rows_cover_all_k_values_and_select_none():
    documents, _, _ = load_corpus("dev")
    document = next(item for item in documents if item["task_id"] == "p15_persistence_001")
    rows = _metric_rows([], document, {})
    assert tuple(int(value) for value in rows) == K_VALUES
    assert all(value["precision"] == 0.0 for value in rows.values())
    assert all(value["recall"] == 0.0 for value in rows.values())


def test_metric_rows_perfect_selection_has_no_noise():
    documents, _, _ = load_corpus("dev")
    document = next(item for item in documents if item["task_id"] == "p15_persistence_001")
    selected = document["expected_context"]["required"] + document["expected_context"]["useful"]
    rows = _metric_rows(selected, document, {})
    assert rows["1"]["precision"] == 1.0
    assert rows["3"]["precision"] == 1.0
    assert rows["5"]["noise_ratio"] == 0.0
    assert rows["10"]["noise_ratio"] == 0.0


def test_duplicate_provider_ids_are_evidence_failure():
    result = SimpleNamespace(selected_items=[SimpleNamespace(id="a"), SimpleNamespace(id="a")])
    with pytest.raises(W06C0Error, match="duplicate"):
        _select_ids(result, ["a"])


def test_safety_gates_cover_scope_lifecycle_forbidden_and_secret():
    task = SimpleNamespace(project_id="project-a", forbidden=("forbidden",), inactive_allowed=False)
    metadata = {
        "foreign": {"project_id": "project-b", "status": "active", "content": "safe"},
        "forbidden": {"project_id": "project-a", "status": "active", "content": "safe"},
        "old": {"project_id": "project-a", "status": "superseded", "content": "safe"},
        "resolved": {"project_id": "project-a", "status": "resolved", "content": "safe"},
        "secret": {"project_id": "project-a", "status": "active", "content": "api_key=secret-value"},
    }
    counts = _safety(task, tuple(metadata), metadata)
    assert counts == {
        "wrong_project_leakage": 1,
        "forbidden_leakage": 1,
        "superseded_leakage": 1,
        "resolved_leakage": 1,
        "secret_leakage": 1,
    }


def test_optional_slots_are_explicitly_not_measured_and_report_is_content_free():
    report = run_matrix(split="dev", providers=("embedding", "reranker"))
    assert set(report["providers"]) == {"embedding", "reranker"}
    assert all(item["run_status"] == "NOT_MEASURED" for item in report["providers"].values())
    rendered = json.dumps(report, ensure_ascii=False, sort_keys=True)
    assert "Record the future authority decision" not in rendered
    assert "Markdown is the canonical" not in rendered


def test_zero_answerable_split_is_explicitly_not_a_quality_pass():
    report = run_matrix(split="test", providers=("v1",))
    assert report["quality"] == {"answerable_count": 0, "state": "INSUFFICIENT_ANSWERABLE_CASES"}
    assert report["providers"]["v1"]["quality_state"] == "INSUFFICIENT_ANSWERABLE_CASES"
    assert report["providers"]["v1"]["metrics"]["1"]["precision"] is None


def test_explicit_optional_probe_uses_configured_embedding_adapter(monkeypatch):
    class FakeEmbedding:
        provider_id = "fake-embedding"
        model = "fake-model"

        def embed(self, texts):
            return SimpleNamespace(
                status="EMBEDDING_AVAILABLE",
                provider_id=self.provider_id,
                model=self.model,
                vectors=tuple((1.0, 0.0) for _ in texts),
            )

    monkeypatch.setattr("evals.w06c0.evaluation.create_embedding_provider", lambda: FakeEmbedding())
    report = run_matrix(split="dev", providers=("embedding",), measure_optional=True)
    provider = report["providers"]["embedding"]
    assert provider["availability"] == "AVAILABLE"
    assert provider["run_status"] == "COMPLETE"
    assert provider["actual_provider_id"] == "fake-embedding"
    assert "token_waste" in provider["metrics"]["1"]


def test_scope_gate_rejects_forbidden_revision_changes():
    evidence = verify_scope_diff()
    assert evidence["allowlist_status"] == "PASS"
    assert evidence["forbidden_paths"] == []
    assert evidence["scope_end_revision"] == IMPLEMENTATION_SCOPE_END_REVISION


def test_scope_gate_rejects_invalid_or_non_ancestor_end_revision():
    with pytest.raises(W06C0Error, match="cannot verify"):
        verify_scope_diff(scope_end_revision="0" * 40)
    with pytest.raises(W06C0Error, match="base is not an ancestor"):
        verify_scope_diff(scope_end_revision="5c296912953e32dc60988cdc270ef4c3b268db9f")


def test_core_provider_matrix_has_identical_snapshot_and_zero_safety():
    report = run_matrix(split="dev", providers=("v1", "w06b", "v2", "authority_lexical"))
    providers = report["providers"]
    snapshots = {
        (
            value["source_memory_revision"],
            value["candidate_content_fingerprint"],
            value["candidate_order_fingerprint"],
        )
        for value in providers.values()
    }
    assert len(snapshots) == 1
    assert all(not any(value["safety"].values()) for value in providers.values())
    assert all(value["run_status"] == "COMPLETE" for value in providers.values())


def test_holdout_requires_final_audit_confirmation():
    with pytest.raises(W06C0Error, match="holdout"):
        run_matrix(split="holdout", providers=("embedding",))


def test_invalid_answerability_status_fails_closed():
    with pytest.raises(W06C0Error, match="status/reason"):
        _answerability(
            {
                "answerability": {
                    "status": "YES",
                    "reason": "query_and_candidate_metadata_support_target",
                    "review_version": "w06c0-v1",
                    "provenance_hash": "sha256:" + "0" * 64,
                    "reviewers": ["a", "b"],
                }
            }
        )
