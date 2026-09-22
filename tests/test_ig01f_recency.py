"""Frozen IG01-F provider, projection, safety, and HOLDOUT gates."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from evals.ig01f.corpus import (
    DEFAULT_OUTPUT,
    SOURCE_ROOT,
    CorpusProjectionError,
    build_projection,
    check_projection,
)
from evals.ig01f.measure import MeasurementError, _load, validate_evidence
from evals.ig01f.provider import RecencyContinuityProvider
from evals.ig01c.engine import evaluate_corpus, validate_report


PINNED_HOLDOUT_SHA256 = "8afb7d3964a806cc04d606a7e49891f1fed53d72fd06b01c1e5dbd13c8504fa1"


def _rows(name: str = "dev.jsonl"):
    return [json.loads(line) for line in (DEFAULT_OUTPUT / name).read_text(encoding="utf-8").splitlines()]


def _vault(tmp_path: Path, row: dict) -> Path:
    root = tmp_path / "vault"
    target = root / ".claude" / "validated-memory.json"
    target.parent.mkdir(parents=True)
    target.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "revision": 0,
                "updated_at": "2025-01-01T00:00:00Z",
                "validated_at": "2025-01-01T00:00:00Z",
                "summary": {"source": "ig01f_test"},
                "validated_memory": row["memories"],
                "rejected_memory": [],
            }
        ),
        encoding="utf-8",
    )
    return root


def _task(row: dict, text: str | None = None):
    return SimpleNamespace(task_id=row["case_id"], project_id=row["project_id"], prompt=text or row["task_text"])


def test_projection_is_byte_deterministic_and_committed():
    first = build_projection()
    second = build_projection()
    assert first == second
    check_projection()


def test_projection_refuses_holdout_before_path_access(monkeypatch):
    opened = []
    original = Path.read_text

    def watched(path, *args, **kwargs):
        opened.append(str(path))
        assert "holdout" not in str(path).casefold()
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", watched)
    build_projection()
    assert opened
    with pytest.raises(CorpusProjectionError, match="HOLDOUT"):
        from evals.ig01f.corpus import _safe_source_path

        _safe_source_path(SOURCE_ROOT, "holdout")


def test_holdout_manifest_pin_is_unchanged_without_opening_holdout():
    manifest = json.loads((SOURCE_ROOT / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["holdout_sha256"] == PINNED_HOLDOUT_SHA256
    assert manifest["file_sha256"]["holdout"] == PINNED_HOLDOUT_SHA256


def test_query_blind_deterministic_and_read_only(tmp_path):
    row = _rows()[0]
    vault = _vault(tmp_path, row)
    provider = RecencyContinuityProvider()
    before = (vault / ".claude" / "validated-memory.json").read_bytes()
    first = provider.select(_task(row, "first unrelated task"), vault)
    second = provider.select(_task(row, "different task text"), vault)
    after = (vault / ".claude" / "validated-memory.json").read_bytes()
    assert [item.id for item in first.selected_items] == [item.id for item in second.selected_items]
    assert first.as_dict() == second.as_dict()
    assert before == after


def test_scope_and_lifecycle_leakage_are_zero(tmp_path):
    for category in ("wrong_project_candidate", "superseded_memory", "resolved_blocker"):
        row = next(item for item in _rows() if item["category"] == category)
        vault = _vault(tmp_path / category, row)
        selected = RecencyContinuityProvider().select(_task(row), vault)
        assert set(item.id for item in selected.selected_items).issubset(set(row["candidate_ids"]))
        for item in selected.selected_items:
            assert item.project_id in {None, row["project_id"]}
            assert item.status == "active"


def test_budget_is_enforced_on_exact_rendered_selection(tmp_path):
    row = _rows()[0]
    for index, memory in enumerate(row["memories"]):
        memory["content"] = f"record-{index}-" + ("x" * 500)
    vault = _vault(tmp_path, row)
    provider = RecencyContinuityProvider(max_context_tokens=64, minimum_headroom_tokens=8, hard_byte_limit=256)
    result = provider.select(_task(row), vault)
    assert result.selected_items == ()


def test_projection_contains_all_public_phenomena_and_languages():
    rows = _rows() + _rows("validation.jsonl")
    source_manifest = json.loads((SOURCE_ROOT / "manifest.json").read_text(encoding="utf-8"))
    assert {row["category"] for row in rows} == set(source_manifest["phenomena"])
    assert {row["language"] for row in rows} == set(source_manifest["languages"])
    assert len(rows) == 114


def test_projection_has_no_label_bearing_candidate_ids_or_content():
    for row in _rows() + _rows("validation.jsonl") + _rows("abstention.jsonl"):
        for memory in row["memories"]:
            payload = json.dumps(memory, sort_keys=True).casefold()
            assert "-answer" not in payload
            assert "-distractor" not in payload
            assert memory["memory_id"] in row["candidate_ids"]
            assert memory["memory_id"].startswith("mem-ig01f-")
            assert len(memory["memory_id"]) == len("mem-ig01f-") + 20


def _evidence_envelope():
    summary = {"leakage": {name: 0 for name in (
        "forbidden_leakage", "wrong_project_leakage", "superseded_leakage", "resolved_leakage"
    )}}
    provider = {
        "aggregate": summary,
        "by_phenomenon": {},
        "by_language": {},
        "case_results": [],
        "controls": {},
    }
    return {
        "schema_version": 1,
        "report_type": "ig01f-naive-baseline-evidence",
        "source": {"git_sha": "a" * 40, "source_fingerprint": "sha256:" + "b" * 64,
                   "corpus_version": "ig01f-recency-v1", "splits": ["dev", "validation"],
                   "holdout_included": False},
        "budget": {},
        "providers": {name: copy.deepcopy(provider) for name in ("v1", "v2", "recency")},
        "paired": {"recency_vs_v1": {}, "recency_vs_v2": {}},
        "abstention": {},
    }


def test_measurement_contract_rejects_holdout_and_tampered_leakage():
    with pytest.raises(MeasurementError, match="HOLDOUT"):
        _load("holdout")
    evidence = _evidence_envelope()
    assert validate_evidence(evidence, source_bound=False) == evidence
    evidence["providers"]["recency"]["aggregate"]["leakage"]["forbidden_leakage"] = 1
    with pytest.raises(MeasurementError, match="leakage"):
        validate_evidence(evidence, source_bound=False)


def test_measurement_contract_is_closed():
    evidence = _evidence_envelope()
    evidence["unexpected"] = True
    with pytest.raises(MeasurementError, match="envelope"):
        validate_evidence(evidence, source_bound=False)


def test_ig01c_controls_expose_select_everything_gaming():
    row = next(
        item for item in _rows()
        if item["required_ids"] and len(item["candidate_ids"]) > len(item["required_ids"])
    )
    report = evaluate_corpus(
        [row],
        {row["case_id"]: {"retrieved_ids": row["candidate_ids"]}},
        corpus_version="ig01f-recency-v1",
        split="dev",
        retrieval_k=5,
        enforce_benchmark=False,
    )
    validate_report(report)
    control = report["controls"][row["case_id"]]
    assert control["select_all"]["metrics"]["recall_at_k"]["value"] == 1.0
    assert control["select_all"]["metrics"]["precision_at_k"]["value"] < 1.0
    assert control["select_all"]["metrics"]["noise_ratio"]["value"] > 0.0
    assert control["select_none"]["selected_ids"] == []


def test_evidence_rejects_source_fingerprint_tampering(monkeypatch):
    evidence = _evidence_envelope()
    monkeypatch.setattr("evals.ig01f.measure._source_git_sha", lambda: "a" * 40)
    monkeypatch.setattr("evals.ig01f.measure._fingerprint", lambda: "sha256:" + "c" * 64)
    with pytest.raises(MeasurementError, match="fingerprint"):
        validate_evidence(evidence)
