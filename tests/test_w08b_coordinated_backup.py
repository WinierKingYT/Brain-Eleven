"""Focused evidence for W-08B's stable coordinated backup boundary."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

import memory_backup as backup
from memory_backup import (
    CANONICAL_ARCHIVE_PATH,
    MemoryBackupConsistencyError,
    MemoryBackupError,
    SETTINGS_ARCHIVE_PATH,
    create_backup,
    verify_backup,
)


def _vault(tmp_path: Path, *, settings: bool = True) -> Path:
    vault = tmp_path / "vault"
    claude = vault / ".claude"
    claude.mkdir(parents=True)
    document = {
        "schema_version": 2,
        "revision": 4,
        "updated_at": "2026-09-13T00:00:00Z",
        "validated_at": "2026-09-13T00:00:00Z",
        "summary": {},
        "validated_memory": [],
        "rejected_memory": [],
    }
    (claude / "validated-memory.json").write_text(json.dumps(document), encoding="utf-8")
    if settings:
        (claude / "settings.json").write_text(
            json.dumps({"sentinel": "private-settings-value"}), encoding="utf-8"
        )
    return vault


def _write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value), encoding="utf-8")


def _ensure_optional_sources(vault: Path, source: str) -> None:
    claude = vault / ".claude"
    if source in {backup.REGISTRY_ARCHIVE_PATH, backup.STATE_ARCHIVE_PATH}:
        _write_json(
            claude / "project-registry.json",
            {
                "schema_version": 1,
                "revision": 2,
                "updated_at": "2026-09-13T00:00:00Z",
                "projects": [],
            },
        )
    if source == backup.STATE_ARCHIVE_PATH:
        _write_json(
            claude / "project-state.json",
            {
                "schema_version": 1,
                "store_revision": 0,
                "updated_at": "2026-09-13T00:00:00Z",
                "projects": {},
                "events": [],
            },
        )


def _mutate_valid_source(vault: Path, source: str) -> None:
    path = vault / backup.RESTORE_PATHS[source]
    document = json.loads(path.read_text(encoding="utf-8"))
    if source == backup.CANONICAL_ARCHIVE_PATH:
        document["revision"] += 1
    elif source == backup.REGISTRY_ARCHIVE_PATH:
        document["revision"] += 1
    elif source == backup.STATE_ARCHIVE_PATH:
        document["store_revision"] += 1
    else:
        document["sentinel"] = "rewritten"
    _write_json(path, document)


def _manifest(archive: Path) -> dict:
    with zipfile.ZipFile(archive) as handle:
        return json.loads(handle.read("manifest.json"))


def test_v3_manifest_descriptors_and_digest_match_archived_bytes(tmp_path):
    vault = _vault(tmp_path)
    archive = tmp_path / "backup.zip"

    result = create_backup(vault, archive)

    assert result["status"] == "created"
    manifest = _manifest(archive)
    assert manifest["schema_version"] == 3
    snapshot = manifest["snapshot"]
    assert snapshot["protocol"] == backup.SNAPSHOT_PROTOCOL
    assert snapshot["attempts"] == 1
    assert set(snapshot["sources"]) == set(backup.SOURCE_ARCHIVE_PATHS)
    assert snapshot["sources"][backup.STATE_ARCHIVE_PATH]["present"] is False
    assert snapshot["sources"][backup.SETTINGS_ARCHIVE_PATH]["sha256"]
    assert snapshot["source_snapshot_sha256"] == backup._source_snapshot_digest(snapshot["sources"])
    assert verify_backup(archive)["status"] == "verified"


def test_absent_optional_sources_are_explicit_in_v3_snapshot(tmp_path):
    vault = _vault(tmp_path, settings=False)
    archive = tmp_path / "backup.zip"

    create_backup(vault, archive)
    snapshot = _manifest(archive)["snapshot"]["sources"]

    for source in backup.OPTIONAL_SOURCE_PATHS:
        assert snapshot[source]["present"] is False
        assert snapshot[source]["sha256"] is None
        assert snapshot[source]["bytes"] == 0


def test_one_shot_optional_source_change_retries_to_stable_archive(tmp_path, monkeypatch):
    vault = _vault(tmp_path)
    archive = tmp_path / "backup.zip"
    original = backup._read_source_pass
    calls = 0

    def mutate_after_first_pass(path):
        nonlocal calls
        value = original(path)
        calls += 1
        if calls == 1:
            (vault / ".claude" / "settings.json").write_text(
                json.dumps({"sentinel": "new-value"}), encoding="utf-8"
            )
        return value

    monkeypatch.setattr(backup, "_read_source_pass", mutate_after_first_pass)
    create_backup(vault, archive)

    manifest = _manifest(archive)
    assert manifest["snapshot"]["attempts"] == 2
    assert manifest["snapshot"]["sources"][SETTINGS_ARCHIVE_PATH]["sha256"] == backup._sha256(
        (vault / ".claude" / "settings.json").read_bytes()
    )


@pytest.mark.parametrize(
    "source",
    [
        backup.CANONICAL_ARCHIVE_PATH,
        backup.REGISTRY_ARCHIVE_PATH,
        backup.SETTINGS_ARCHIVE_PATH,
        backup.STATE_ARCHIVE_PATH,
    ],
)
def test_each_source_revision_or_hash_churn_is_retried(tmp_path, monkeypatch, source):
    vault = _vault(tmp_path)
    _ensure_optional_sources(vault, source)
    archive = tmp_path / f"{source.split('/')[0]}.zip"
    original = backup._read_source_pass
    calls = 0

    def mutate_once(path):
        nonlocal calls
        value = original(path)
        calls += 1
        if calls == 1:
            _mutate_valid_source(vault, source)
        return value

    monkeypatch.setattr(backup, "_read_source_pass", mutate_once)
    create_backup(vault, archive)
    assert _manifest(archive)["snapshot"]["attempts"] == 2


def test_optional_source_appearance_and_disappearance_are_bounded_changes(tmp_path, monkeypatch):
    real_read = backup._read_source_pass
    vault = _vault(tmp_path, settings=False)
    source = backup.STATE_ARCHIVE_PATH
    archive = tmp_path / "appeared.zip"
    calls = 0

    def appear(path):
        nonlocal calls
        value = real_read(path)
        calls += 1
        if calls == 1:
            _ensure_optional_sources(vault, source)
        return value

    monkeypatch.setattr(backup, "_read_source_pass", appear)
    create_backup(vault, archive)
    assert _manifest(archive)["snapshot"]["sources"][source]["present"] is True

    vault = _vault(tmp_path / "second", settings=True)
    archive = tmp_path / "disappeared.zip"
    calls = 0

    def disappear(path):
        nonlocal calls
        value = real_read(path)
        calls += 1
        if calls == 1:
            (vault / ".claude" / "settings.json").unlink()
        return value

    monkeypatch.setattr(backup, "_read_source_pass", disappear)
    create_backup(vault, archive)
    assert _manifest(archive)["snapshot"]["sources"][SETTINGS_ARCHIVE_PATH]["present"] is False


def test_perpetual_source_churn_is_bounded_and_publishes_nothing(tmp_path, monkeypatch):
    vault = _vault(tmp_path)
    output = tmp_path / "backup.zip"
    original = backup._read_source_pass
    calls = 0

    def churn(path):
        nonlocal calls
        value = original(path)
        calls += 1
        (vault / ".claude" / "settings.json").write_text(
            json.dumps({"sentinel": f"churn-{calls}"}), encoding="utf-8"
        )
        return value

    monkeypatch.setattr(backup, "_read_source_pass", churn)
    with pytest.raises(MemoryBackupConsistencyError) as raised:
        create_backup(vault, output)
    error = raised.value
    assert error.attempts == backup.MAX_SNAPSHOT_ATTEMPTS
    assert error.reason == "optional_source_changed"
    assert error.changed_sources == (SETTINGS_ARCHIVE_PATH,)
    assert not output.exists()
    assert "private-settings-value" not in str(error)
    assert "churn" not in str(error)
    assert calls == backup.MAX_SNAPSHOT_ATTEMPTS * 2


def test_snapshot_attempt_budget_has_typed_bounded_error(tmp_path, monkeypatch):
    vault = _vault(tmp_path)
    output = tmp_path / "backup.zip"
    ticks = iter((0.0, 5.1))
    monkeypatch.setattr(backup.time, "monotonic", lambda: next(ticks))

    with pytest.raises(MemoryBackupConsistencyError) as raised:
        create_backup(vault, output)
    assert raised.value.reason == "read_budget_exceeded"
    assert raised.value.attempts == 1
    assert not output.exists()


def test_stable_corruption_remains_explicit_and_does_not_retry(tmp_path):
    vault = _vault(tmp_path)
    (vault / ".claude" / "settings.json").write_text("not-json", encoding="utf-8")

    with pytest.raises(MemoryBackupError, match="settings"):
        create_backup(vault, tmp_path / "backup.zip")


def test_validation_error_does_not_echo_project_identity(tmp_path):
    vault = _vault(tmp_path, settings=False)
    document = json.loads(
        (vault / ".claude" / "validated-memory.json").read_text(encoding="utf-8")
    )
    document["validated_memory"] = [
        {
            "memory_id": "mem-private",
            "type": "decision",
            "content": "A private decision",
            "scope": "project",
            "project": "Private project",
            "project_label": "Private project",
            "project_id": "project-secret-identifier",
            "status": "active",
            "confidence": 0.9,
            "quality_score": 0.9,
            "timestamp": "2026-09-13T00:00:00Z",
            "is_approved": True,
            "dedup_fingerprint": "wrong",
        }
    ]
    _write_json(vault / ".claude" / "validated-memory.json", document)

    with pytest.raises(MemoryBackupError) as raised:
        create_backup(vault, tmp_path / "backup.zip")
    assert "project-secret-identifier" not in str(raised.value)


def test_schema2_archive_still_verifies_without_snapshot_metadata(tmp_path):
    vault = _vault(tmp_path)
    source = tmp_path / "v3.zip"
    legacy = tmp_path / "v2.zip"
    create_backup(vault, source)

    with zipfile.ZipFile(source) as original, zipfile.ZipFile(legacy, "w") as target:
        manifest = json.loads(original.read("manifest.json"))
        manifest["schema_version"] = 2
        manifest.pop("snapshot")
        target.writestr("manifest.json", json.dumps(manifest))
        for name in original.namelist():
            if name != "manifest.json":
                target.writestr(name, original.read(name))

    assert verify_backup(legacy)["status"] == "verified"


def test_publication_sync_failure_leaves_no_archive_or_temp_file(tmp_path, monkeypatch):
    vault = _vault(tmp_path)
    output = tmp_path / "backup.zip"

    def fail_sync(_path):
        raise OSError("simulated directory sync failure")

    monkeypatch.setattr(backup, "_fsync_parent_directory", fail_sync)
    with pytest.raises(MemoryBackupError, match="Cannot create backup archive"):
        create_backup(vault, output)
    assert not output.exists()
    assert not list(tmp_path.glob(".memory-backup-*.zip"))


def test_source_symlink_is_rejected_before_archive_publication(tmp_path):
    vault = _vault(tmp_path)
    source = vault / ".claude" / "validated-memory.json"
    target = vault / ".claude" / "real-memory.json"
    source.rename(target)
    try:
        source.symlink_to(target)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"symlink creation unavailable: {exc}")

    with pytest.raises(MemoryBackupError, match="symbolic link"):
        create_backup(vault, tmp_path / "backup.zip")
    assert not (tmp_path / "backup.zip").exists()


@pytest.mark.parametrize("kind", ["vault", "claude"])
def test_vault_and_claude_symlinks_are_rejected(tmp_path, kind):
    real = _vault(tmp_path / "real")
    try:
        if kind == "vault":
            candidate = tmp_path / "vault-link"
            target = real
            candidate.symlink_to(target, target_is_directory=True)
        else:
            candidate = tmp_path / "vault-link"
            candidate.mkdir()
            target = real / ".claude"
            (candidate / ".claude").symlink_to(target, target_is_directory=True)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"symlink creation unavailable: {exc}")

    with pytest.raises(MemoryBackupError, match="symbolic link"):
        create_backup(candidate, tmp_path / f"{kind}.zip")
