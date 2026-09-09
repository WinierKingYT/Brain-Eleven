"""IG-01-B corpus, hash, answerability, and privacy-boundary checks."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from evals.ig01b.failures import empty_manifest, ingest_failure, validate_failure_case
from evals.ig01b.generator import PUBLIC_ROOT
from evals.ig01b.integrity import (
    assert_private_path,
    check_public_corpus,
    verify_holdout_hash,
)
from evals.ig01b.private import repository_leak_candidates
from evals.ig01b.private import write_private_case


def test_public_corpus_matrix_and_holdout_are_complete():
    report = check_public_corpus(PUBLIC_ROOT)
    assert report["total_answerable"] == 153
    assert report["matrix_cells"] == 51
    assert report["matrix_minimum"] >= 3
    assert 30 <= report["splits"]["holdout"] <= 50
    assert report["inter_annotator_disagreement_rate"] <= 0.15
    assert report["secret_hits"] == 0
    assert report["pii_hits"] == 0


def test_holdout_hash_matches_manifest_and_sidecar():
    assert verify_holdout_hash(PUBLIC_ROOT)
    from evals.ig01b.integrity import verify_holdout_tag
    assert verify_holdout_tag(PUBLIC_ROOT)
    manifest = json.loads((PUBLIC_ROOT / "manifest.json").read_text(encoding="utf-8"))
    sidecar = (PUBLIC_ROOT / "holdout.sha256").read_text(encoding="utf-8").split()[0]
    assert sidecar == manifest["holdout_sha256"]


def test_abstention_set_is_separate_from_answerable_cases():
    lines = (PUBLIC_ROOT / "abstention.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 6
    cases = [json.loads(line) for line in lines]
    assert all(case["case_kind"] == "abstention" for case in cases)
    assert all(case["answerability"]["status"] == "unanswerable" for case in cases)


def test_private_boundary_has_no_repository_leak():
    repository_root = Path(__file__).resolve().parents[1]
    assert repository_leak_candidates(repository_root) == []
    assert_private_path(repository_root / "evals" / "private", repository_root)
    with pytest.raises(ValueError, match="outside|public"):
        assert_private_path(repository_root / "evals" / "ig01b" / "public", repository_root)


def test_sanitized_failure_ingestion_is_strict_and_reserved_for_ig08(tmp_path: Path):
    manifest = empty_manifest()
    assert manifest["cases"] == 0
    assert "IG-08" in manifest["status"]
    case = {
        "failure_id": "FAIL-001",
        "taxonomy": "RETRIEVAL_NOISE",
        "corpus_version": "ig-failures-v1",
        "sanitized": True,
        "project_hash": "sha256:project",
        "task_hash": "sha256:task",
        "expected": {"required_ids": ["mem-1"]},
        "actual": {"selected_ids": ["mem-2"]},
        "root_cause": "ranking_signal",
        "provenance": {"source": "dogfood-turn-hash"},
        "sanitization": ["remove raw prompt", "hash project and task", "remove memory content"],
    }
    path = ingest_failure(case, tmp_path)
    assert path.exists()
    with pytest.raises(ValueError, match="raw prompt"):
        validate_failure_case({**case, "prompt": "private"})


def test_private_realistic_writer_requires_same_ground_truth_schema(tmp_path: Path):
    public_case = json.loads((PUBLIC_ROOT / "dev.jsonl").read_text(encoding="utf-8").splitlines()[0])
    public_case["dataset_class"] = "PRIVATE_REALISTIC"
    public_case["provenance"]["privacy_status"] = "local-only-sanitized"
    public_case["query_hash"] = "sha256:query"
    public_case.pop("query")
    path = write_private_case(tmp_path, public_case)
    assert path.parent == (tmp_path / "evals" / "private").resolve()
    with pytest.raises(ValueError, match="PRIVATE_REALISTIC"):
        write_private_case(tmp_path, {**public_case, "dataset_class": "PUBLIC_SYNTHETIC"})
