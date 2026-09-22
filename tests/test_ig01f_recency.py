"""Frozen IG01-F provider, projection, safety, and HOLDOUT gates."""

from __future__ import annotations

import copy
import builtins
import json
import os
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
from evals.ig01f.measure import MeasurementError, _load, build_evidence, validate_evidence
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


def test_forbidden_rejected_memory_is_never_a_provider_candidate(tmp_path):
    row = copy.deepcopy(_rows()[0])
    forbidden = copy.deepcopy(row["memories"][0])
    forbidden["memory_id"] = "mem-ig01f-forbidden00"
    forbidden["content"] = "Forbidden rejected record must never be selected."
    forbidden["updated_at"] = "2099-01-01T00:00:00Z"
    vault = _vault(tmp_path, row)
    memory_path = vault / ".claude" / "validated-memory.json"
    document = json.loads(memory_path.read_text(encoding="utf-8"))
    document["rejected_memory"] = [forbidden]
    memory_path.write_text(json.dumps(document), encoding="utf-8")

    result = RecencyContinuityProvider().select(_task(row), vault)

    assert forbidden["memory_id"] not in {item.id for item in result.selected_items}


def test_resolved_canonical_blocker_is_never_a_provider_candidate(tmp_path):
    row = copy.deepcopy(_rows()[0])
    resolved = copy.deepcopy(row["memories"][0])
    resolved["memory_id"] = "mem-ig01f-resolved000"
    resolved["type"] = "blocker"
    resolved["content"] = "Resolved canonical blocker must never be selected."
    resolved["status"] = "resolved"
    resolved["updated_at"] = "2099-01-01T00:00:00Z"
    resolved["resolved_at"] = "2099-01-01T00:00:01Z"
    resolved["resolved_by"] = "ig01f-test"
    resolved["resolution_note"] = "closed before provider selection"
    vault = _vault(tmp_path, row)
    memory_path = vault / ".claude" / "validated-memory.json"
    document = json.loads(memory_path.read_text(encoding="utf-8"))
    document["validated_memory"].append(resolved)
    memory_path.write_text(json.dumps(document), encoding="utf-8")

    provider = RecencyContinuityProvider()
    candidate_ids = {item.id for item in provider._candidate_items(_task(row), vault)}
    selected_ids = {item.id for item in provider.select(_task(row), vault).selected_items}

    assert any(
        item["memory_id"] == resolved["memory_id"] and item["status"] == "resolved"
        for item in json.loads(memory_path.read_text(encoding="utf-8"))["validated_memory"]
    )
    assert resolved["memory_id"] not in candidate_ids
    assert resolved["memory_id"] not in selected_ids


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


def _committed_evidence():
    path = Path("evals/ig01f/ig01f-naive-baseline-evidence.json")
    return json.loads(path.read_text(encoding="utf-8"))


def test_measurement_contract_rejects_holdout_and_tampered_leakage():
    with pytest.raises(MeasurementError, match="HOLDOUT"):
        _load("holdout")
    evidence = _committed_evidence()
    assert validate_evidence(evidence, source_bound=False) == evidence
    evidence["providers"]["recency"]["aggregate"]["leakage"]["forbidden_leakage"] = 1
    with pytest.raises(MeasurementError, match="leakage"):
        validate_evidence(evidence, source_bound=False)


def test_measurement_contract_is_closed():
    evidence = _committed_evidence()
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
    evidence = _committed_evidence()
    monkeypatch.setattr("evals.ig01f.measure._source_git_sha", lambda: evidence["source"]["git_sha"])
    monkeypatch.setattr("evals.ig01f.measure._fingerprint", lambda: "sha256:" + "c" * 64)
    with pytest.raises(MeasurementError, match="fingerprint"):
        validate_evidence(evidence)


def test_evidence_rejects_nested_metric_and_paired_tampering(monkeypatch):
    evidence = _committed_evidence()
    pristine = copy.deepcopy(evidence)
    monkeypatch.setattr("evals.ig01f.measure._source_git_sha", lambda: pristine["source"]["git_sha"])
    monkeypatch.setattr("evals.ig01f.measure._fingerprint", lambda: pristine["source"]["source_fingerprint"])
    monkeypatch.setattr("evals.ig01f.measure._build_evidence_payload", lambda: copy.deepcopy(pristine))

    tampered_reports = []
    aggregate = copy.deepcopy(pristine)
    aggregate["providers"]["v1"]["aggregate"]["mrr"] = 0.123456
    tampered_reports.append(aggregate)
    phenomenon = copy.deepcopy(pristine)
    phenomenon["providers"]["v2"]["by_phenomenon"]["correction"]["recall_at_k"] = 0.999999
    tampered_reports.append(phenomenon)
    language = copy.deepcopy(pristine)
    language["providers"]["recency"]["by_language"]["tr"]["noise_ratio"] = 0.111111
    tampered_reports.append(language)
    abstention = copy.deepcopy(pristine)
    abstention["abstention"]["v2"]["empty_selection_count"] -= 1
    tampered_reports.append(abstention)
    paired = copy.deepcopy(pristine)
    paired["paired"]["recency_vs_v2"]["wins"] -= 1
    paired["paired"]["recency_vs_v2"]["ties"] += 1
    tampered_reports.append(paired)

    for report in tampered_reports:
        with pytest.raises(MeasurementError, match="deterministic regeneration"):
            validate_evidence(report)


def test_measurement_runner_never_opens_holdout(monkeypatch):
    opened = []
    original_builtin_open = builtins.open
    original_path_open = Path.open
    original_os_open = os.open

    def guard_path(path):
        rendered = os.fspath(path)
        if isinstance(rendered, bytes):
            rendered = os.fsdecode(rendered)
        opened.append(rendered)
        assert "holdout" not in rendered.casefold(), f"HOLDOUT access attempted: {rendered}"

    def watched_builtin_open(file, *args, **kwargs):
        guard_path(file)
        return original_builtin_open(file, *args, **kwargs)

    def watched_path_open(path, *args, **kwargs):
        guard_path(path)
        return original_path_open(path, *args, **kwargs)

    def watched_os_open(path, *args, **kwargs):
        guard_path(path)
        return original_os_open(path, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", watched_builtin_open)
    monkeypatch.setattr(Path, "open", watched_path_open)
    monkeypatch.setattr(os, "open", watched_os_open)

    report = build_evidence()
    assert report["source"]["holdout_included"] is False
    assert opened
