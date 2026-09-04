"""Graduation tests for verified canonical-memory backup and restore."""

import json
import sys
import zipfile
from pathlib import Path

import pytest


SCRIPTS = Path(__file__).parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

from entity_extractor import EntityExtractor  # noqa: E402
from memory_backup import (  # noqa: E402
    CANONICAL_ARCHIVE_PATH,
    MemoryBackupError,
    REGISTRY_ARCHIVE_PATH,
    SETTINGS_ARCHIVE_PATH,
    STATE_ARCHIVE_PATH,
    create_backup,
    restore_backup,
    run_disaster_drill,
    verify_backup,
)
from memory_scope import GLOBAL_SCOPE, PROJECT_SCOPE, scoped_fingerprint  # noqa: E402
from memory_store import MemoryStore  # noqa: E402
from project_registry import ProjectRegistry  # noqa: E402
from state_store import StateService  # noqa: E402


def _memory(memory_id, content, *, scope=GLOBAL_SCOPE, project_id="", project="", status="active"):
    return {
        "memory_id": memory_id,
        "type": "decision",
        "content": content,
        "scope": scope,
        "project": project,
        "project_label": project,
        "project_id": project_id,
        "status": status,
        "confidence": 0.9,
        "quality_score": 0.9,
        "timestamp": "2026-09-02T12:00:00Z",
        "is_approved": True,
        "dedup_fingerprint": scoped_fingerprint(content, scope, project_id, "decision"),
    }


@pytest.fixture
def source_vault(tmp_path):
    vault = tmp_path / "source-vault"
    claude = vault / ".claude"
    claude.mkdir(parents=True)
    alpha_root = tmp_path / "alpha-project"
    beta_root = tmp_path / "beta-project"
    alpha_root.mkdir()
    beta_root.mkdir()

    registry = ProjectRegistry(vault)
    registry.register(alpha_root, project_id="proj-alpha", project_label="Alpha")
    registry.register(beta_root, project_id="proj-beta", project_label="Beta")

    canonical = {
        "schema_version": 2,
        "revision": 7,
        "updated_at": "2026-09-02T12:00:00Z",
        "validated_at": "2026-09-02T12:00:00Z",
        "summary": {"validated": 4},
        "validated_memory": [
            _memory("mem-global", "Always write canonical JSON atomically."),
            _memory(
                "mem-alpha",
                "Alpha persists project settings in SQLite.",
                scope=PROJECT_SCOPE,
                project_id="proj-alpha",
                project="Alpha",
            ),
            _memory(
                "mem-beta",
                "Beta persists world state in region files.",
                scope=PROJECT_SCOPE,
                project_id="proj-beta",
                project="Beta",
            ),
            _memory(
                "mem-alpha-old",
                "Alpha used an obsolete JSON settings file.",
                scope=PROJECT_SCOPE,
                project_id="proj-alpha",
                project="Alpha",
                status="superseded",
            ),
        ],
        "rejected_memory": [],
    }
    (claude / "validated-memory.json").write_text(
        json.dumps(canonical, indent=2), encoding="utf-8"
    )
    (claude / "settings.json").write_text(
        json.dumps({"memory": {"autoSave": True}}), encoding="utf-8"
    )
    return vault


def test_backup_manifest_contains_only_canonical_state(source_vault, tmp_path):
    archive = tmp_path / "memory-foundation.zip"

    result = create_backup(source_vault, archive)

    assert result["status"] == "created"
    assert result["canonical_revision"] == 7
    assert result["memory_count"] == 4
    with zipfile.ZipFile(archive) as backup:
        names = set(backup.namelist())
        assert names == {
            "manifest.json",
            CANONICAL_ARCHIVE_PATH,
            REGISTRY_ARCHIVE_PATH,
            SETTINGS_ARCHIVE_PATH,
        }
        manifest = json.loads(backup.read("manifest.json"))
    assert manifest["migration"]["name"] == "scope-v2"
    assert manifest["canonical"]["project_count"] == 2


def test_restore_preserves_identity_then_rebuilds_derived_state(source_vault, tmp_path):
    archive = tmp_path / "memory-foundation.zip"
    restored_vault = tmp_path / "blank-vault"
    source_canonical = (source_vault / ".claude" / "validated-memory.json").read_bytes()
    source_registry = (source_vault / ".claude" / "project-registry.json").read_bytes()

    create_backup(source_vault, archive)
    result = restore_backup(archive, restored_vault)

    assert result["status"] == "restored"
    assert (restored_vault / ".claude" / "validated-memory.json").read_bytes() == source_canonical
    assert (restored_vault / ".claude" / "project-registry.json").read_bytes() == source_registry
    assert not (restored_vault / ".claude" / "knowledge-graph.json").exists()
    assert not (restored_vault / ".claude" / "context-bootstrap.json").exists()

    restored = MemoryStore(restored_vault).load()
    assert restored["revision"] == 7
    assert [memory["memory_id"] for memory in restored["validated_memory"]] == [
        "mem-global", "mem-alpha", "mem-beta", "mem-alpha-old"
    ]
    assert restored["validated_memory"][-1]["status"] == "superseded"
    assert ProjectRegistry(restored_vault).get("proj-alpha")["project_id"] == "proj-alpha"

    graph = EntityExtractor(str(restored_vault)).build_graph()
    assert graph.projection_status()["status"] == "fresh"


def test_backup_restore_preserves_canonical_project_state_when_present(source_vault, tmp_path):
    service = StateService(source_vault)
    source = {"type": "user", "reference": "backup-test"}
    service.init_project("proj-alpha", source=source, now="2026-09-03T12:00:00Z")
    service.set_current_milestone(
        "proj-alpha",
        phase_id="phase-16",
        title="Task + State Model",
        expected_revision=1,
        source=source,
        record_id="mil_backup_state",
        now="2026-09-03T12:00:00Z",
    )
    archive = tmp_path / "canonical-with-state.zip"
    restored_vault = tmp_path / "restored-with-state"

    created = create_backup(source_vault, archive)
    with zipfile.ZipFile(archive) as backup:
        assert STATE_ARCHIVE_PATH in backup.namelist()
    restored = restore_backup(archive, restored_vault)

    assert created["state_project_count"] == 1
    assert restored["state_project_count"] == 1
    restored_state = StateService(restored_vault).store.get_project("proj-alpha")
    assert restored_state["revision"] == 2
    assert restored_state["current"]["milestone"]["phase_id"] == "phase-16"


def test_disaster_drill_rebuilds_context_without_cross_project_leakage(source_vault, tmp_path):
    archive = tmp_path / "drill.zip"

    result = run_disaster_drill(source_vault, archive, project_id="proj-alpha")

    assert result["status"] == "passed"
    assert result["canonical_revision"] == 7
    assert result["wrong_project_leakage"] == 0
    assert {"mem-global", "mem-alpha"}.issubset(result["selected_memory_ids"])
    assert "mem-beta" not in result["selected_memory_ids"]
    assert "mem-alpha-old" not in result["selected_memory_ids"]


def test_tampered_or_unmanifested_archive_is_refused(source_vault, tmp_path):
    archive = tmp_path / "memory-foundation.zip"
    create_backup(source_vault, archive)
    with zipfile.ZipFile(archive, "a") as backup:
        backup.writestr("unexpected.txt", "not in manifest")

    with pytest.raises(MemoryBackupError, match="unmanifested"):
        verify_backup(archive)
    with pytest.raises(MemoryBackupError):
        restore_backup(archive, tmp_path / "must-not-exist")


def test_restore_never_overwrites_and_matching_restore_is_idempotent(source_vault, tmp_path):
    archive = tmp_path / "memory-foundation.zip"
    target = tmp_path / "restored-vault"
    occupied = tmp_path / "occupied-vault"
    create_backup(source_vault, archive)

    occupied.mkdir()
    sentinel = occupied / "do-not-overwrite.txt"
    sentinel.write_text("keep", encoding="utf-8")
    with pytest.raises(MemoryBackupError, match="must not exist"):
        restore_backup(archive, occupied)
    assert sentinel.read_text(encoding="utf-8") == "keep"

    assert restore_backup(archive, target)["status"] == "restored"
    assert restore_backup(archive, target)["status"] == "already_restored"


def test_backup_refuses_project_memory_without_a_registry(tmp_path):
    vault = tmp_path / "invalid-vault"
    claude = vault / ".claude"
    claude.mkdir(parents=True)
    document = MemoryStore.empty_document()
    document["revision"] = 1
    document["validated_memory"] = [
        _memory(
            "mem-orphaned-project",
            "This provenance must not be orphaned.",
            scope=PROJECT_SCOPE,
            project_id="proj-missing",
            project="Missing",
        )
    ]
    (claude / "validated-memory.json").write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(MemoryBackupError, match="requires a project registry"):
        create_backup(vault, tmp_path / "should-not-exist.zip")


def test_backup_never_overwrites_a_previous_archive(source_vault, tmp_path):
    archive = tmp_path / "memory-foundation.zip"
    archive.write_bytes(b"preserve this backup")

    with pytest.raises(MemoryBackupError, match="Refusing to overwrite"):
        create_backup(source_vault, archive)
    assert archive.read_bytes() == b"preserve this backup"
