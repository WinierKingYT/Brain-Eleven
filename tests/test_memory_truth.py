"""PRE-06 metadata-first truth and lifecycle tests."""

from __future__ import annotations

import json

from memory_truth import MemoryTruthEngine, TruthAction, TruthStatus


def _store(vault, memories, revision=4):
    path = vault / ".claude" / "validated-memory.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"schema_version": 2, "revision": revision, "validated_memory": memories, "rejected_memory": []}), encoding="utf-8")
    return path


def _memory(memory_id, content, *, project_id="brain-eleven", status="active", fingerprint="fp", claim_key=""):
    return {
        "memory_id": memory_id,
        "type": "decision",
        "content": content,
        "status": status,
        "scope": "project",
        "project_id": project_id,
        "dedup_fingerprint": fingerprint,
        "claim_key": claim_key,
    }


def test_duplicate_is_scoped_and_does_not_cross_project(tmp_path):
    _store(tmp_path, [_memory("mem_a", "Use Redis", fingerprint="same", project_id="project-a")])
    engine = MemoryTruthEngine(tmp_path)
    result = engine.process([{"candidate_id": "cand-b", "content": "Use Redis", "memory_type": "decision", "scope": "project", "project_id": "project-b", "dedup_fingerprint": "same", "confidence": 1.0}])
    assert result.status == TruthStatus.SUCCESS.value
    assert result.decisions[0].action == TruthAction.NEW.value


def test_active_claim_key_conflict_does_not_fabricate_winner(tmp_path):
    _store(tmp_path, [_memory("mem_a", "Use PostgreSQL", fingerprint="old", claim_key="db:selected")])
    result = MemoryTruthEngine(tmp_path).process([{"candidate_id": "cand-b", "content": "Use SQLite", "memory_type": "decision", "scope": "project", "project_id": "brain-eleven", "dedup_fingerprint": "new", "claim_key": "db:selected", "confidence": 1.0}])
    assert result.decisions[0].action == TruthAction.CONFLICT.value


def test_explicit_supersession_mutates_only_target_and_preserves_revision_contract(tmp_path):
    path = _store(tmp_path, [_memory("mem_old", "Use PostgreSQL", fingerprint="old")])
    result = MemoryTruthEngine(tmp_path).process([{"candidate_id": "cand-new", "content": "Use SQLite", "memory_type": "decision", "scope": "project", "project_id": "brain-eleven", "operation": "SUPERSEDE_EXISTING", "target_memory_id": "mem_old", "successor_memory_id": "mem_new", "confidence": 1.0, "note": "Explicit correction"}], commit=True)
    assert result.status == TruthStatus.SUCCESS.value
    persisted = json.loads(path.read_text(encoding="utf-8"))
    old = persisted["validated_memory"][0]
    assert old["status"] == "superseded"
    assert old["superseded_by"] == "mem_new"
    assert persisted["revision"] == 5


def test_ambiguous_lifecycle_target_is_review_and_secret_is_rejected(tmp_path):
    _store(tmp_path, [])
    result = MemoryTruthEngine(tmp_path).process([
        {"candidate_id": "missing-target", "content": "Use SQLite", "operation": "SUPERSEDE_EXISTING", "confidence": 1.0},
        {"candidate_id": "secret", "content": "API_KEY=not-for-memory", "confidence": 1.0},
    ])
    assert result.decisions[0].action == TruthAction.REVIEW_REQUIRED.value
    assert result.decisions[1].action == TruthAction.REJECT.value


def test_corrupt_canonical_is_not_empty_success(tmp_path):
    path = tmp_path / ".claude" / "validated-memory.json"
    path.parent.mkdir(parents=True)
    path.write_text("{broken", encoding="utf-8")
    result = MemoryTruthEngine(tmp_path).process([])
    assert result.status == TruthStatus.FAILED.value
    assert result.error_code == "MEMORY_STORE_CORRUPT"
