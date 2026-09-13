"""Focused W-08A tests for registry revision, durability and rollback."""

from __future__ import annotations

import json

import pytest

import project_registry as legacy_registry
from brain_eleven.projects import registry as package_registry


def _registry_document(registry):
    return json.loads(registry.path.read_text(encoding="utf-8"))


def test_schema_one_legacy_file_normalizes_revision_and_upgrades_on_write(tmp_path):
    registry = legacy_registry.ProjectRegistry(tmp_path / "vault")
    registry.path.parent.mkdir(parents=True)
    legacy = {
        "schema_version": 1,
        "updated_at": "2026-09-12T00:00:00Z",
        "projects": [
            {
                "project_id": "proj_legacy",
                "project_label": "Legacy",
                "root": str(tmp_path / "project"),
                "status": "active",
                "proactive_capture": False,
                "created_at": "2026-09-12T00:00:00Z",
                "updated_at": "2026-09-12T00:00:00Z",
            }
        ],
    }
    registry.path.write_text(json.dumps(legacy), encoding="utf-8")

    loaded = registry.load()
    assert loaded["schema_version"] == 1
    assert loaded["revision"] == 0
    assert loaded["projects"] == legacy["projects"]
    assert "revision" not in json.loads(registry.path.read_text(encoding="utf-8"))

    registry.rename("proj_legacy", "Upgraded")
    persisted = _registry_document(registry)
    assert persisted["schema_version"] == 1
    assert persisted["revision"] == 1
    assert persisted["projects"][0]["project_label"] == "Upgraded"


def test_two_writers_stale_conflict_then_explicit_retry(tmp_path):
    registry = legacy_registry.ProjectRegistry(tmp_path / "vault")
    root_a = tmp_path / "a"
    root_b = tmp_path / "b"
    root_a.mkdir()
    root_b.mkdir()
    registry.register(root_a, project_id="proj-a")
    starting_revision = registry.load()["revision"]

    first = legacy_registry.ProjectRegistry(tmp_path / "vault")
    second = legacy_registry.ProjectRegistry(tmp_path / "vault")
    first.register(root_b, project_id="proj-b", expected_revision=starting_revision)

    with pytest.raises(legacy_registry.ProjectRegistryConflict) as conflict:
        second.rename("proj-a", "Stale rename", expected_revision=starting_revision)
    assert conflict.value.expected_revision == starting_revision
    assert conflict.value.actual_revision == starting_revision + 1
    assert second.get("proj-a")["project_label"] != "Stale rename"

    retry_revision = second.load()["revision"]
    second.rename("proj-a", "Retried rename", expected_revision=retry_revision)
    assert second.get("proj-a")["project_label"] == "Retried rename"
    assert second.load()["revision"] == retry_revision + 1


def test_legacy_callers_without_expected_revision_use_latest_snapshot(tmp_path):
    registry = legacy_registry.ProjectRegistry(tmp_path / "vault")
    root = tmp_path / "project"
    root.mkdir()

    first = registry.register(root, project_id="proj-a")
    assert first["project_id"] == "proj-a"
    registry.set_proactive_capture("proj-a", True)
    assert registry.load()["revision"] == 2


def test_mutation_writes_fixed_backup_envelope_and_rollback_is_monotonic(tmp_path):
    registry = legacy_registry.ProjectRegistry(tmp_path / "vault")
    root = tmp_path / "project"
    root.mkdir()
    registry.register(
        root,
        project_id="proj-a",
        project_label="Original",
        status="active",
        proactive_capture=False,
    )
    registry.set_proactive_capture("proj-a", True)
    registry.set_status("proj-a", "archived")
    before_rollback_projection = {
        key: registry.get("proj-a")[key]
        for key in ("project_id", "project_label", "root", "status", "proactive_capture")
    }
    registry.rename("proj-a", "Changed")

    envelope = json.loads(registry.backup_path.read_text(encoding="utf-8"))
    assert envelope["backup_schema_version"] == 1
    assert envelope["source_revision"] == 3
    assert envelope["registry"]["projects"][0]["project_label"] == "Original"
    assert envelope["registry"]["revision"] == 3

    current_revision = registry.load()["revision"]
    result = registry.rollback(expected_revision=current_revision)
    assert result["status"] == "rolled_back"
    assert result["revision"] == current_revision + 1
    restored = registry.get("proj-a")
    assert {
        key: restored[key]
        for key in ("project_id", "project_label", "root", "status", "proactive_capture")
    } == before_rollback_projection
    assert registry.load()["revision"] == current_revision + 1

    repeated = registry.rollback(expected_revision=result["revision"])
    assert repeated["status"] == "already_restored"
    assert repeated["revision"] == result["revision"]


def test_rollback_rejects_stale_revision_and_preserves_current_document(tmp_path):
    registry = legacy_registry.ProjectRegistry(tmp_path / "vault")
    root = tmp_path / "project"
    root.mkdir()
    registry.register(root, project_id="proj-a")
    registry.rename("proj-a", "Changed")
    current_revision = registry.load()["revision"]
    before = registry.path.read_bytes()

    registry.set_status("proj-a", "archived")
    with pytest.raises(legacy_registry.ProjectRegistryConflict):
        registry.rollback(expected_revision=current_revision)
    assert registry.path.read_bytes() != before
    assert registry.get("proj-a")["status"] == "archived"


def test_corrupt_or_missing_backup_is_explicit(tmp_path):
    registry = legacy_registry.ProjectRegistry(tmp_path / "vault")
    root = tmp_path / "project"
    root.mkdir()
    registry.register(root, project_id="proj-a")

    with pytest.raises(legacy_registry.ProjectRegistryBackupError):
        registry.rollback(expected_revision=registry.load()["revision"])

    registry.rename("proj-a", "Changed")
    registry.backup_path.write_text("not json", encoding="utf-8")
    with pytest.raises(legacy_registry.ProjectRegistryBackupError):
        registry.rollback(expected_revision=registry.load()["revision"])


def test_fsync_failure_does_not_report_success(monkeypatch, tmp_path):
    registry = legacy_registry.ProjectRegistry(tmp_path / "vault")
    root = tmp_path / "project"
    root.mkdir()
    registry.register(root, project_id="proj-a")
    before = registry.path.read_bytes()

    def fail_fsync(_descriptor):
        raise OSError("synthetic fsync failure")

    monkeypatch.setattr(legacy_registry.os, "fsync", fail_fsync)
    with pytest.raises(legacy_registry.ProjectRegistryBackupError):
        registry.rename("proj-a", "Should not commit")
    assert registry.path.read_bytes() == before


def test_main_persistence_failure_is_typed_and_preserves_previous_bytes(monkeypatch, tmp_path):
    registry = legacy_registry.ProjectRegistry(tmp_path / "vault")
    root = tmp_path / "project"
    root.mkdir()
    registry.register(root, project_id="proj-a")
    before = registry.path.read_bytes()
    original_atomic_write = legacy_registry._atomic_write

    def fail_main(path, data):
        if path == registry.path:
            raise OSError("synthetic replace failure")
        return original_atomic_write(path, data)

    monkeypatch.setattr(legacy_registry, "_atomic_write", fail_main)
    with pytest.raises(legacy_registry.ProjectRegistryError, match="Cannot persist project registry"):
        registry.rename("proj-a", "Should not commit")
    assert registry.path.read_bytes() == before


def test_atomic_write_invokes_parent_directory_sync_hook(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(
        legacy_registry,
        "_fsync_parent_directory",
        lambda path: calls.append(path),
    )
    registry = legacy_registry.ProjectRegistry(tmp_path / "vault")
    root = tmp_path / "project"
    root.mkdir()
    registry.register(root, project_id="proj-a")
    assert calls == [registry.path]


def test_package_and_legacy_exports_preserve_identity(tmp_path):
    import project_registry as bare_registry

    assert package_registry.ProjectRegistry is legacy_registry.ProjectRegistry
    assert package_registry.ProjectRegistry is bare_registry.ProjectRegistry
    assert package_registry.ProjectRegistryConflict is legacy_registry.ProjectRegistryConflict
    assert package_registry.ProjectRegistryBackupError is legacy_registry.ProjectRegistryBackupError
    assert package_registry.registry_backup_path(tmp_path) == legacy_registry.registry_backup_path(tmp_path)
