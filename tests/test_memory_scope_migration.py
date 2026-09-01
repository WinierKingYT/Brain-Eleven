"""Recovery-focused tests for the explicit memory-scope migration."""

import importlib.util
import json
import sys
from pathlib import Path

import pytest


SCRIPTS = Path(__file__).parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

from memory_scope import (  # noqa: E402
    GLOBAL_SCOPE,
    PROJECT_SCOPE,
    legacy_project_id,
    scoped_fingerprint,
)


def _load_migration():
    spec = importlib.util.spec_from_file_location(
        "memory_scope_migration", SCRIPTS / "migrate-memory-scope.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def vault(tmp_path):
    vault_path = tmp_path / "vault"
    (vault_path / ".claude").mkdir(parents=True)
    return vault_path


def _memory_path(vault):
    return vault / ".claude" / "validated-memory.json"


def _write_document(vault, document):
    path = _memory_path(vault)
    path.write_text(json.dumps(document, indent=2), encoding="utf-8")
    return path


def test_dry_run_and_migration_handle_mixed_legacy_records_without_identity_loss(vault):
    migration = _load_migration()
    alpha_id = legacy_project_id("Alpha")
    document = {
        "schema_version": 1,
        "revision": 7,
        "validated_memory": [
            {"memory_id": None, "type": "lesson", "content": "Legacy global lesson"},
            {
                "memory_id": "legacy-alpha",
                "type": "decision",
                "content": "Legacy Alpha decision",
                "project": "Alpha",
            },
            {
                "memory_id": "already-v2",
                "type": "observation",
                "content": "Current scoped observation",
                "scope": PROJECT_SCOPE,
                "project": "Alpha",
                "project_label": "Alpha",
                "project_id": alpha_id,
                "dedup_fingerprint": scoped_fingerprint(
                    "Current scoped observation", PROJECT_SCOPE, alpha_id, "observation"
                ),
            },
        ],
        "rejected_memory": [
            {"memory_id": "rejected-global", "type": "observation", "content": "Rejected legacy"},
        ],
    }
    path = _write_document(vault, document)
    before = path.read_bytes()

    preview = migration.migrate(vault, dry_run=True)

    assert preview["status"] == "dry_run"
    assert preview["source_revision"] == preview["revision"] == 7
    assert preview["needs_review"] == []
    assert path.read_bytes() == before

    result = migration.migrate(vault)
    migrated = json.loads(path.read_text(encoding="utf-8"))

    assert result["status"] == "migrated"
    assert result["source_revision"] == 7
    assert result["revision"] == 8
    assert migrated["schema_version"] == 2
    assert migrated["validated_memory"][0]["memory_id"] is None
    assert migrated["validated_memory"][0]["scope"] == GLOBAL_SCOPE
    assert migrated["validated_memory"][1]["project_id"] == alpha_id
    assert migrated["validated_memory"][2]["memory_id"] == "already-v2"
    assert migrated["rejected_memory"][0]["scope"] == GLOBAL_SCOPE


def test_duplicate_fingerprint_cluster_is_preserved_without_data_loss(vault):
    migration = _load_migration()
    _write_document(vault, {
        "validated_memory": [
            {"memory_id": "first", "type": "lesson", "content": "Same legacy content"},
            {"memory_id": "second", "type": "lesson", "content": "Same legacy content"},
        ],
        "rejected_memory": [],
    })

    result = migration.migrate(vault)
    stored = json.loads(_memory_path(vault).read_text(encoding="utf-8"))

    assert result["status"] == "migrated"
    assert [memory["memory_id"] for memory in stored["validated_memory"]] == ["first", "second"]
    assert len({memory["dedup_fingerprint"] for memory in stored["validated_memory"]}) == 1


def test_schema_v1_envelope_is_persisted_as_v2_even_when_records_are_current(vault):
    migration = _load_migration()
    document = {
        "schema_version": 1,
        "revision": 4,
        "validated_memory": [{
            "memory_id": "current-global",
            "type": "lesson",
            "content": "Already scoped global memory",
            "scope": GLOBAL_SCOPE,
            "project": "",
            "project_label": "",
            "project_id": "",
            "dedup_fingerprint": scoped_fingerprint(
                "Already scoped global memory", GLOBAL_SCOPE, "", "lesson"
            ),
        }],
        "rejected_memory": [],
    }
    path = _write_document(vault, document)
    before = path.read_bytes()

    result = migration.migrate(vault)
    stored = json.loads(path.read_text(encoding="utf-8"))

    assert result["status"] == "migrated"
    assert result["changed"] == 0
    assert result["schema_upgraded"] is True
    assert result["revision"] == 5
    assert stored["schema_version"] == 2
    assert Path(result["backup"]).read_bytes() == before


def test_ambiguous_project_scope_is_reported_without_persisting_a_guess(vault):
    migration = _load_migration()
    path = _write_document(vault, {
        "validated_memory": [{
            "memory_id": "ambiguous",
            "type": "decision",
            "content": "No project identity is available",
            "scope": PROJECT_SCOPE,
        }],
        "rejected_memory": [],
    })
    before = path.read_bytes()

    preview = migration.migrate(vault, dry_run=True)
    result = migration.migrate(vault)

    assert preview["status"] == result["status"] == "needs_review"
    assert result["needs_review"] == [{
        "bucket": "validated_memory",
        "index": 0,
        "memory_id": "ambiguous",
        "reason": "project_scope_without_identity",
    }]
    assert path.read_bytes() == before
    assert not list(path.parent.glob("*.pre-scope-v2-*.bak"))


def test_malformed_record_stops_before_backup_or_write(vault):
    migration = _load_migration()
    path = _write_document(vault, {
        "validated_memory": ["not-a-memory-object"],
        "rejected_memory": [],
    })
    before = path.read_bytes()

    with pytest.raises(migration.MemoryScopeMigrationError):
        migration.migrate(vault)

    assert path.read_bytes() == before
    assert not list(path.parent.glob("*.pre-scope-v2-*.bak"))


def test_interrupted_migration_preserves_canonical_then_reruns_and_rolls_back(vault, monkeypatch):
    migration = _load_migration()
    source = {
        "validated_memory": [{
            "memory_id": "stable-id",
            "type": "decision",
            "content": "Legacy project decision",
            "project": "Legacy Project",
        }],
        "rejected_memory": [],
    }
    path = _write_document(vault, source)
    before = path.read_bytes()

    with monkeypatch.context() as patch:
        patch.setattr(
            migration.MemoryStore,
            "_write_unlocked",
            lambda _self, _data: (_ for _ in ()).throw(OSError("simulated disk failure")),
        )
        with pytest.raises(OSError, match="simulated disk failure"):
            migration.migrate(vault)

    backups = list(path.parent.glob("*.pre-scope-v2-*.bak"))
    assert len(backups) == 1
    assert backups[0].read_bytes() == before
    assert path.read_bytes() == before

    migrated = migration.migrate(vault)
    rerun = migration.migrate(vault)
    rolled_back = migration.rollback(vault, migrated["backup"])
    restored = json.loads(path.read_text(encoding="utf-8"))

    assert migrated["status"] == "migrated"
    assert rerun["status"] == "unchanged"
    assert rolled_back["status"] == "rolled_back"
    assert rolled_back["revision"] == 2
    assert restored["validated_memory"] == source["validated_memory"]
    assert restored["rejected_memory"] == source["rejected_memory"]


def test_invalid_rollback_backup_never_replaces_canonical_memory(vault):
    migration = _load_migration()
    path = _write_document(vault, {
        "validated_memory": [{"memory_id": "safe", "type": "lesson", "content": "Safe memory"}],
        "rejected_memory": [],
    })
    before = path.read_bytes()
    invalid_backup = vault / "invalid-backup.json"
    invalid_backup.write_text("{not valid json", encoding="utf-8")

    with pytest.raises(migration.MemoryScopeMigrationError):
        migration.rollback(vault, invalid_backup)

    assert path.read_bytes() == before
