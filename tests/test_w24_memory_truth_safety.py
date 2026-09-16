"""W-24 direct memory-truth safety, scope, and provenance evidence."""

from __future__ import annotations

import ast
import dataclasses
import importlib
import json
from pathlib import Path

import pytest

from brain_eleven.memory import MemoryStore
from brain_eleven.memory.truth import (
    MemoryTruthEngine,
    TruthAction,
    TruthCandidate,
    TruthStatus,
    legacy_request_projection,
)
from brain_eleven.projects.registry import ProjectRegistry, registry_path
from brain_eleven.runtime.migration import migrate
from brain_eleven.runtime.storage import identity
from brain_eleven.runtime.worker import _memory_candidate_values


LEGACY_FIELDS = (
    "candidate_id",
    "content",
    "memory_type",
    "scope",
    "project_id",
    "project",
    "dedup_fingerprint",
    "claim_key",
    "commitment",
    "confidence",
    "evidence_refs",
    "occurred_at",
    "operation",
    "target_memory_id",
    "successor_memory_id",
    "resolved_by",
    "note",
)


def _project(vault: Path, project_id: str = "project-a", *, enabled: bool = True):
    root = vault / ("root-" + project_id)
    root.mkdir(parents=True, exist_ok=True)
    return ProjectRegistry(vault).register(
        root,
        project_id=project_id,
        project_label="Label " + project_id,
        proactive_capture=enabled,
    )


def _candidate(project_id: str = "project-a", **overrides):
    value = {
        "candidate_id": "candidate-a",
        "content": "The queue uses SQLite as its local source of truth.",
        "memory_type": "decision",
        "scope": "project",
        "project_id": project_id,
        "confidence": 1.0,
    }
    value.update(overrides)
    return value


def _record(memory_id: str = "mem-target", project_id: str = "project-a"):
    return {
        "memory_id": memory_id,
        "type": "decision",
        "content": "The queue uses PostgreSQL.",
        "status": "active",
        "scope": "project",
        "project_id": project_id,
        "project": "Label " + project_id,
        "project_label": "Label " + project_id,
        "dedup_fingerprint": "target-fingerprint",
        "claim_key": "queue:database",
    }


def _write_record(vault: Path, record=None):
    return MemoryStore(vault).append(record or _record())


def _secret_cases():
    return (
        "-----BEGIN PRIVATE KEY-----\n" + "A" * 24,
        "Authorization: Bearer " + "a" * 24,
        "ghp_" + "a" * 24,
        "client_secret=" + "a" * 24,
        "password=" + "a" * 12,
        "Authorization: Basic " + "A" * 16,
        "session_id=" + "a" * 24,
        "postgres://user:" + "a" * 12 + "@host/db",
    )


def test_truth_surfaces_and_safety_policy_keep_identity():
    legacy = importlib.import_module("memory_truth")
    capture = importlib.import_module("capture_safety")
    package = importlib.import_module("brain_eleven.memory.truth")

    for name in (
        "TruthError",
        "TruthInputError",
        "TruthCorruptError",
        "TruthAction",
        "TruthStatus",
        "TruthCandidate",
        "TruthDecision",
        "TruthResult",
        "MemoryTruthEngine",
        "legacy_request_projection",
    ):
        assert getattr(package, name) is getattr(legacy, name)
    assert legacy.evaluate_capture is capture.evaluate_capture


def test_truth_script_contains_no_second_write_authority():
    path = Path(__file__).parents[1] / "scripts" / "memory_truth.py"
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    assert not any(
        isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name in {"write_json", "_write_unlocked", "_atomic_write"}
        for node in ast.walk(tree)
    )
    assert "json.dump(" not in source
    assert "write_text(" not in source
    assert "_SECRET" not in source


@pytest.mark.parametrize("content", _secret_cases())
def test_all_shared_secret_families_reject_before_any_canonical_effect(tmp_path, content):
    result = MemoryTruthEngine(tmp_path).process(
        [{"candidate_id": "secret-case", "content": content, "confidence": 1.0}],
        commit=True,
        commit_new=True,
    )
    assert result.status == TruthStatus.DEGRADED.value
    assert result.decisions[0].action == TruthAction.REJECT.value
    assert result.decisions[0].reason_code == "SECRET_CONTENT"
    assert MemoryStore(tmp_path).revision() == 0
    assert not (tmp_path / ".claude" / "validated-memory.backup.json").exists()


def test_shared_policy_limits_and_safe_controls_are_preserved(tmp_path):
    too_large = MemoryTruthEngine(tmp_path).process(
        [{"candidate_id": "large", "content": "x" * 6001}],
    )
    too_many_lines = MemoryTruthEngine(tmp_path).process(
        [{"candidate_id": "lines", "content": "\n".join("x" for _ in range(81))}],
    )
    transcript = MemoryTruthEngine(tmp_path).process(
        [{
            "candidate_id": "transcript",
            "content": "\n".join("user: " + "x" * 100 for _ in range(4)),
        }],
    )
    assert too_large.decisions[0].reason_code == "CAPTURE_TOO_LARGE"
    assert too_many_lines.decisions[0].reason_code == "CAPTURE_TOO_MANY_LINES"
    assert transcript.decisions[0].reason_code == "CAPTURE_TRANSCRIPT_LIKE"
    safe = MemoryTruthEngine(tmp_path).process(
        [{"candidate_id": "safe", "content": "Security discussions contain no credentials."}],
    )
    assert safe.decisions[0].action == TruthAction.NEW.value


def test_lifecycle_note_uses_the_same_safety_gate_before_target_mutation(tmp_path):
    _project(tmp_path)
    _write_record(tmp_path)
    path = MemoryStore(tmp_path).path
    before_bytes = path.read_bytes()
    result = MemoryTruthEngine(tmp_path).process(
        [_candidate(
            operation="SUPERSEDE_EXISTING",
            target_memory_id="mem-target",
            successor_memory_id="mem-successor",
            note="Authorization: Bearer " + "a" * 24,
        )],
        commit=True,
        commit_new=True,
    )
    assert result.decisions[0].reason_code == "SECRET_CONTENT"
    assert path.read_bytes() == before_bytes
    assert MemoryStore(tmp_path).revision() == 1
    assert not (tmp_path / ".claude" / "validated-memory.backup.json").exists()


@pytest.mark.parametrize(
    ("setup", "reason"),
    (
        ("missing", "PROJECT_UNREGISTERED"),
        ("archived", "PROJECT_ARCHIVED"),
        ("disabled", "PROJECT_CAPTURE_DISABLED"),
    ),
)
def test_project_registry_negative_states_fail_closed_without_memory_effect(tmp_path, setup, reason):
    if setup != "missing":
        _project(tmp_path, enabled=setup != "disabled")
        if setup == "archived":
            ProjectRegistry(tmp_path).set_status("project-a", "archived")
    result = MemoryTruthEngine(tmp_path).process(
        [_candidate()],
        commit=True,
        commit_new=True,
    )
    assert result.status == TruthStatus.DEGRADED.value
    assert result.decisions[0].reason_code == reason
    assert MemoryStore(tmp_path).revision() == 0
    assert not (tmp_path / ".claude" / "validated-memory.backup.json").exists()


@pytest.mark.parametrize("registry_payload", (b"{broken", b'{"schema_version": 99}'))
def test_registry_unavailable_is_bounded_and_does_not_load_memory(tmp_path, monkeypatch, registry_payload):
    _project(tmp_path)
    registry_path(tmp_path).write_bytes(registry_payload)
    truth = importlib.import_module("scripts.memory_truth")

    def fail_memory_load(self):
        raise AssertionError("memory must not be loaded for unavailable registry")

    monkeypatch.setattr(truth.MemoryStore, "load", fail_memory_load)
    result = MemoryTruthEngine(tmp_path).process(
        [_candidate()],
        commit=True,
        commit_new=True,
    )
    assert result.status == TruthStatus.SCOPE_ERROR.value
    assert result.error_code == "PROJECT_REGISTRY_UNAVAILABLE"
    assert result.decisions[0].reason_code == "PROJECT_REGISTRY_UNAVAILABLE"
    assert MemoryStore(tmp_path).path.exists() is False


def test_global_metadata_is_rejected_without_registry_lookup(tmp_path, monkeypatch):
    truth = importlib.import_module("scripts.memory_truth")

    def fail_registry(*args, **kwargs):
        raise AssertionError("global candidates must not consult the registry")

    monkeypatch.setattr(truth.ProjectRegistry, "get", fail_registry)
    result = MemoryTruthEngine(tmp_path).process(
        [{"candidate_id": "global", "content": "safe", "project_label": "wrong"}],
        commit=True,
        commit_new=True,
    )
    assert result.decisions[0].reason_code == "GLOBAL_PROJECT_METADATA"
    assert MemoryStore(tmp_path).revision() == 0


def test_active_registry_owns_project_label_and_user_provenance(tmp_path):
    project = _project(tmp_path)
    result = MemoryTruthEngine(tmp_path).process(
        [_candidate(project["project_id"], project="caller-label", source="user", is_approved=True)],
        commit=True,
        commit_new=True,
    )
    assert result.status == TruthStatus.SUCCESS.value
    record = MemoryStore(tmp_path).load()["validated_memory"][0]
    assert record["project_id"] == project["project_id"]
    assert record["project"] == project["project_label"]
    assert record["project_label"] == project["project_label"]
    assert record["source"] == "user"
    assert record["is_approved"] is True


def test_provenance_rejections_have_no_effect_and_commitment_still_gates(tmp_path):
    _project(tmp_path)
    false_approval = MemoryTruthEngine(tmp_path).process(
        [_candidate(is_approved=False)],
        commit=True,
        commit_new=True,
    )
    uncommitted = MemoryTruthEngine(tmp_path).process(
        [_candidate(commitment="UNCERTAIN", is_approved=True)],
        commit=True,
        commit_new=True,
    )
    invalid_source = MemoryTruthEngine(tmp_path).process(
        [_candidate(source="model")],
        commit=True,
        commit_new=True,
    )
    assert false_approval.decisions[0].reason_code == "UNAPPROVED_CANDIDATE"
    assert uncommitted.decisions[0].reason_code == "UNCOMMITTED_CANDIDATE"
    assert invalid_source.status == TruthStatus.INVALID_INPUT.value
    assert invalid_source.error_code == "INVALID_PROVENANCE"
    assert MemoryStore(tmp_path).revision() == 0


def test_truth_candidate_shape_and_legacy_projection_are_immutable():
    assert tuple(field.name for field in dataclasses.fields(TruthCandidate)) == LEGACY_FIELDS
    candidate = TruthCandidate.from_mapping(_candidate())
    projected = legacy_request_projection(candidate)
    assert tuple(projected) == LEGACY_FIELDS
    assert tuple(dataclasses.asdict(candidate)) == LEGACY_FIELDS
    assert "source" not in projected
    assert "is_approved" not in projected


def test_new_receipt_tracks_provenance_without_changing_request_hash(tmp_path):
    project = _project(tmp_path)
    migrate(tmp_path)
    operation_id = identity("op_", "w24-provenance")
    value = _candidate(project["project_id"], source="user", is_approved=True)
    engine = MemoryTruthEngine(tmp_path)
    first = engine.process([value], commit=True, commit_new=True, operation_id=operation_id)
    document = MemoryStore(tmp_path).load()
    receipt = document["operation_receipts"][operation_id]
    candidate = TruthCandidate.from_mapping(value)
    assert receipt["request_hash"] == identity("request_", [legacy_request_projection(candidate)])
    assert receipt["provenance_hash"] == identity("provenance_", [["user", True]])
    revision = document["revision"]
    replay = engine.process([value], commit=True, commit_new=True, operation_id=operation_id)
    assert [item.to_dict() for item in first.decisions] == [
        item.to_dict() if hasattr(item, "to_dict") else item for item in replay.decisions
    ]
    assert MemoryStore(tmp_path).revision() == revision
    changed = engine.process(
        [{**value, "source": "review"}],
        commit=True,
        commit_new=True,
        operation_id=operation_id,
    )
    assert changed.status == TruthStatus.INVALID_INPUT.value
    assert changed.error_code == "OPERATION_REPLAY_MISMATCH"
    assert MemoryStore(tmp_path).revision() == revision


def test_pre_w24_receipt_replays_only_legacy_shaped_input(tmp_path):
    project = _project(tmp_path)
    migrate(tmp_path)
    operation_id = identity("op_", "w24-legacy-replay")
    value = _candidate(project["project_id"])
    engine = MemoryTruthEngine(tmp_path)
    engine.process([value], commit=True, commit_new=True, operation_id=operation_id)
    path = MemoryStore(tmp_path).path
    document = json.loads(path.read_text(encoding="utf-8"))
    document["operation_receipts"][operation_id].pop("provenance_hash")
    path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    revision = MemoryStore(tmp_path).revision()
    replay = engine.process([value], commit=True, commit_new=True, operation_id=operation_id)
    assert replay.status == TruthStatus.SUCCESS.value
    assert MemoryStore(tmp_path).revision() == revision
    mismatch = engine.process(
        [{**value, "is_approved": True}],
        commit=True,
        commit_new=True,
        operation_id=operation_id,
    )
    assert mismatch.status == TruthStatus.INVALID_INPUT.value
    assert mismatch.error_code == "OPERATION_REPLAY_MISMATCH"
    assert MemoryStore(tmp_path).revision() == revision


def test_worker_unapproved_transition_stays_review_required(tmp_path):
    project = _project(tmp_path)
    candidate = _candidate(project["project_id"], candidate_id="worker-candidate")
    values = _memory_candidate_values(candidate, approved=False)
    result = MemoryTruthEngine(tmp_path).process([values])
    assert values["commitment"] == "UNCERTAIN"
    assert result.decisions[0].action == TruthAction.REVIEW_REQUIRED.value
    assert result.decisions[0].reason_code == "UNCOMMITTED_CANDIDATE"


def test_cli_can_evaluate_without_persisting(tmp_path, capsys):
    module = importlib.import_module("scripts.memory_truth")
    candidate_path = tmp_path / "candidates.json"
    candidate_path.write_text(
        json.dumps([{"candidate_id": "cli", "content": "A safe global decision."}]),
        encoding="utf-8",
    )
    exit_code = module.main(["--vault", str(tmp_path), "--candidates", str(candidate_path)])
    output = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert output["decisions"][0]["action"] == "NEW"
    assert MemoryStore(tmp_path).revision() == 0
