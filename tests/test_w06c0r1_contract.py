"""Focused contract tests for W-06C0R1's immutable corpus boundary."""

import json
from pathlib import Path

import pytest

from evals.w06c0r1.evaluation import (
    K_VALUES,
    W06C0R1Error,
    _attestation_hash,
    _case_payload_hash,
    _metric_rows,
    _safety,
    _verify_attestation,
    candidate_content_fingerprint,
    candidate_order_fingerprint,
    load_corpus,
    run_matrix,
    source_fingerprint,
    task_set_fingerprint,
    verify_manifest,
    verify_scope_diff,
    verify_seal,
)


ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "evals" / "corpus-v4"


def _case(split: str = "dev") -> tuple[dict, dict]:
    case_path = sorted((CORPUS / split).glob("*.json"))[0]
    case = json.loads(case_path.read_text(encoding="utf-8"))
    attestation = json.loads((CORPUS / "attestations" / case_path.name).read_text(encoding="utf-8"))
    return case, attestation


def test_v4_manifest_counts_minima_attestations_and_phenomena():
    manifest = verify_manifest(read_splits=("dev", "test", "holdout"))
    assert manifest["suite_counts"] == {"dev": 60, "test": 60, "holdout": 30}
    assert manifest["minimum_answerable_counts"] == {"dev": 45, "test": 45, "holdout": 22}
    for split in ("dev", "test", "holdout"):
        documents, tasks, loaded = load_corpus(split, allow_holdout=True)
        assert len(documents) == len(tasks) == 60 if split != "holdout" else len(documents) == len(tasks) == 30
        assert loaded["manifest_hash"] == manifest["manifest_hash"]
        assert set(manifest["phenomena_counts"][split]) == {
            "exact_relevant_memory", "paraphrase", "old_critical_decision", "current_state_or_blocker",
            "related_lesson", "recent_irrelevant_distractor", "same_keyword_wrong_meaning",
            "superseded_or_resolved_distractor", "cross_project_distractor",
        }
        assert manifest["split_statistics"][split] == {
            "case_count": len(documents),
            "answerable_count": len(documents),
            "unanswerable_count": 0,
            "review_required_count": 0,
        }


def test_case_and_attestation_hashes_bind_payload_and_decisions():
    case, attestation = _case()
    assert case["answerability"]["case_payload_hash"] == _case_payload_hash(case)
    assert attestation["attestation_hash"] == _attestation_hash(attestation)
    tampered = json.loads(json.dumps(case))
    tampered["task"]["prompt"] += " changed"
    with pytest.raises(W06C0R1Error, match="payload hash"):
        _verify_attestation(tampered, attestation, "dev")

    tampered_attestation = json.loads(json.dumps(attestation))
    tampered_attestation["labelers"][1]["id_hash"] = tampered_attestation["labelers"][0]["id_hash"]
    with pytest.raises(W06C0R1Error, match="distinct"):
        _verify_attestation(case, tampered_attestation, "dev")


def test_holdout_is_sealed_and_not_loaded_without_explicit_unlock():
    with pytest.raises(W06C0R1Error, match="holdout"):
        load_corpus("holdout")
    seal = verify_seal()
    assert seal["state"] == "SEALED"
    assert seal["dev_test_report_hashes"]


def test_explicit_corpus_version_and_source_scope():
    with pytest.raises(W06C0R1Error, match="corpus-v4"):
        run_matrix(corpus_version=3, providers=("v1",))
    assert source_fingerprint(ROOT).startswith("sha256:")
    scope = verify_scope_diff()
    assert scope["status"] == "PASS"
    assert scope["forbidden_paths"] == []
    from evals.w06c0r1 import evaluation

    assert scope["scope_end_revision"] == evaluation.IMPLEMENTATION_SCOPE_END_REVISION
    assert "brain_eleven/runtime/worker.py" in scope["post_end_changed_paths"]
    assert "brain_eleven/runtime/worker.py" not in scope["historical_changed_paths"]
    assert not evaluation._post_scope_owned_paths(scope["post_end_changed_paths"])


def test_scope_end_revision_is_pinned_and_invalid_end_fails_closed():
    from evals.w06c0r1 import evaluation

    with pytest.raises(W06C0R1Error, match="scope end revision"):
        evaluation.verify_scope_diff(scope_end_revision="0" * 40)
    assert evaluation._post_scope_owned_paths(
        ["evals/w06c0r1/evidence/dev.json", "brain_eleven/runtime/worker.py"]
    ) == ("evals/w06c0r1/evidence/dev.json",)


def test_historical_scope_compatibility_is_pinned_and_unpinned_hash_fails(monkeypatch, tmp_path):
    from evals.w06c0r1 import evaluation

    scope = evaluation.verify_scope_diff()
    assert scope["historical_scope_compatibility"]["path"] == "evals/w06c0/evaluation.py"
    metadata = json.loads(evaluation.HISTORICAL_SCOPE_COMPAT_METADATA.read_text(encoding="utf-8"))
    metadata["expected_blob_sha256"] = "sha256:" + ("0" * 64)
    replacement = tmp_path / "historical_scope_compat.json"
    replacement.write_text(json.dumps(metadata), encoding="utf-8")
    monkeypatch.setattr(evaluation, "HISTORICAL_SCOPE_COMPAT_METADATA", replacement)
    with pytest.raises(W06C0R1Error, match="metadata is not pinned"):
        evaluation.verify_scope_diff()

    metadata["expected_blob_sha256"] = evaluation.HISTORICAL_SCOPE_COMPAT_BLOB_SHA256
    metadata["scope_end_revision"] = "0" * 40
    replacement.write_text(json.dumps(metadata), encoding="utf-8")
    with pytest.raises(W06C0R1Error, match="metadata is not pinned"):
        evaluation.verify_scope_diff()


def test_historical_w06c0_scope_end_is_pinned_and_fail_closed():
    from evals.w06c0 import evaluation as historical

    evidence = historical.verify_scope_diff()
    assert evidence["scope_end_revision"] == historical.IMPLEMENTATION_SCOPE_END_REVISION
    with pytest.raises(historical.W06C0Error, match="cannot verify"):
        historical.verify_scope_diff(scope_end_revision="0" * 40)
    with pytest.raises(historical.W06C0Error, match="base is not an ancestor"):
        historical.verify_scope_diff(scope_end_revision="5c296912953e32dc60988cdc270ef4c3b268db9f")


def test_snapshot_fingerprints_change_on_each_identity_mutation():
    rows = [{"candidate_id": "a", "type": "decision", "status": "active", "scope": "global", "project_id": None, "content": "one"}]
    original = candidate_content_fingerprint(rows)
    changed_content = [dict(rows[0], content="two")]
    changed_order = candidate_order_fingerprint(3, ["a", "b"])
    assert candidate_content_fingerprint(changed_content) != original
    assert candidate_order_fingerprint(4, ["a"]) != candidate_order_fingerprint(3, ["a"])
    assert changed_order != candidate_order_fingerprint(3, ["a"])
    assert task_set_fingerprint("dev", ["case-a", "case-b"]) != task_set_fingerprint("dev", ["case-b", "case-a"])
    assert task_set_fingerprint("dev", ["case-a"]) != task_set_fingerprint("test", ["case-a"])


def test_token_waste_is_reported_and_empty_selection_is_zero():
    case, _ = _case()
    required = case["expected_context"]["required"]
    useful = case["expected_context"]["useful"]
    selected = required + useful
    metadata = {memory_id: {"content": "relevant"} for memory_id in selected}
    metadata["noise"] = {"content": "irrelevant extra text"}
    rows = _metric_rows(selected + ["noise"], case, metadata)
    assert "token_waste" in rows["10"]
    assert rows["10"]["token_waste"] > 0.0
    empty = _metric_rows([], case, metadata)
    assert all(row["token_waste"] == 0.0 for row in empty.values())


def test_optional_slots_are_explicit_and_content_free_when_not_opted_in():
    report = run_matrix(split="dev", providers=("embedding", "reranker"), measure_optional=False)
    assert all(value["run_status"] == "NOT_MEASURED" for value in report["providers"].values())
    rendered = json.dumps(report, ensure_ascii=False, sort_keys=True)
    assert "Markdown is the canonical" not in rendered
    assert "Quick Note" not in rendered


def test_explicit_optional_probe_is_unavailable_or_measured_without_fabrication():
    report = run_matrix(split="dev", providers=("embedding", "reranker"), measure_optional=True)
    for value in report["providers"].values():
        assert value["run_status"] in {"COMPLETE", "NOT_MEASURED", "ERROR"}
        if value["run_status"] == "NOT_MEASURED":
            assert value["availability"] == "UNAVAILABLE"
            assert value["metrics"]["1"]["precision"] is None


def test_provider_rows_use_opaque_task_handles_and_shared_fingerprints():
    report = run_matrix(split="dev", providers=("v1", "w06b"))
    providers = report["providers"]
    fingerprints = {
        (value["source_memory_revision"], value["candidate_content_fingerprint"], value["candidate_order_fingerprint"], value["task_set_fingerprint"])
        for value in providers.values()
    }
    assert len(fingerprints) == 1
    for value in providers.values():
        assert all(row["task_handle"].startswith("task-") for row in value["rows"])
        assert not any(row["task_handle"].startswith("v4_") for row in value["rows"])


def test_global_scope_marks_project_memory_as_wrong_project_leakage():
    task = type("Task", (), {"project_id": None, "forbidden": (), "inactive_allowed": False})()
    metadata = {
        "global": {"project_id": None, "status": "active", "content": "global"},
        "project": {"project_id": "other", "status": "active", "content": "project"},
    }
    assert _safety(task, ["global"], metadata)["wrong_project_leakage"] == 0
    assert _safety(task, ["project"], metadata)["wrong_project_leakage"] == 1


def test_holdout_report_binds_seal_and_unlock_hash():
    token = "one-time-test-token"
    report = run_matrix(split="holdout", providers=("v1",), allow_holdout=True, unlock_token=token)
    assert report["holdout_evidence"]["seal_hash"] == verify_seal()["seal_hash"]
    assert report["holdout_evidence"]["unlock_token_hash"].startswith("sha256:")


def test_committed_holdout_evidence_binds_current_seal_and_source():
    artifact = json.loads((ROOT / "evals/w06c0r1/evidence/holdout.json").read_text(encoding="utf-8"))
    assert artifact["holdout_evidence"]["seal_hash"] == verify_seal()["seal_hash"]
    assert artifact["source"]["source_fingerprint"] == source_fingerprint(ROOT)


def test_holdout_cli_replay_is_rejected_before_provider_run(monkeypatch, tmp_path):
    from evals.w06c0r1.evaluation import main

    output = tmp_path / "holdout.json"
    output.write_text("{}", encoding="utf-8")
    monkeypatch.setattr("evals.w06c0r1.evaluation.FINAL_HOLDOUT_OUTPUT", output)
    with pytest.raises(W06C0R1Error, match="replay"):
        main([
            "--corpus-version", "4", "--split", "holdout", "--providers", "v1",
            "--final-holdout", "--unlock-token", "token", "--output", str(output),
        ])


def test_holdout_cli_rejects_noncanonical_output_before_provider_run(monkeypatch, tmp_path):
    from evals.w06c0r1 import evaluation

    def provider_must_not_run(*args, **kwargs):
        raise AssertionError("provider execution must not begin for a non-canonical output")

    monkeypatch.setattr(evaluation, "_run_matrix_provider", provider_must_not_run)
    with pytest.raises(W06C0R1Error, match="canonical evidence path"):
        evaluation.main([
            "--corpus-version", "4", "--split", "holdout", "--providers", "v1",
            "--final-holdout", "--unlock-token", "token",
            "--output", str(tmp_path / "alternate-holdout.json"),
        ])


def test_final_holdout_requires_holdout_split_before_provider_run(monkeypatch, tmp_path):
    from evals.w06c0r1 import evaluation

    def provider_must_not_run(*args, **kwargs):
        raise AssertionError("provider execution must not begin for a non-holdout split")

    monkeypatch.setattr(evaluation, "_run_matrix_provider", provider_must_not_run)
    with pytest.raises(W06C0R1Error, match="requires the holdout split"):
        evaluation.main([
            "--corpus-version", "4", "--split", "dev", "--providers", "v1",
            "--final-holdout", "--unlock-token", "token",
            "--output", str(tmp_path / "alternate-holdout.json"),
        ])


def test_safety_hard_gate_cannot_be_masked(monkeypatch):
    from evals.w06c0r1 import evaluation

    original = evaluation._run_matrix_provider

    def unsafe(*args, **kwargs):
        result = original(*args, **kwargs)
        result["safety"]["wrong_project_leakage"] = 1
        return result

    monkeypatch.setattr(evaluation, "_run_matrix_provider", unsafe)
    with pytest.raises(W06C0R1Error, match="safety hard gate"):
        run_matrix(split="dev", providers=("v1",))
