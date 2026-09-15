"""W-16 tests for the canonical MemoryStore.append() boundary."""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest

from brain_eleven.memory import MemoryStore, MemoryStoreError, MemoryStoreRecordInvalid


def _valid(**overrides):
    value = {
        "memory_id": "mem-valid",
        "type": "lesson",
        "content": "A valid canonical fixture.",
    }
    value.update(overrides)
    return value


@pytest.mark.parametrize(
    "record",
    [
        {},
        {"memory_id": "only-id"},
        {"memory_id": "m", "type": "lesson"},
        {"memory_id": " ", "type": "lesson", "content": "text"},
        {"memory_id": "m", "type": " ", "content": "text"},
        {"memory_id": "m", "type": "lesson", "content": " "},
        {"memory_id": "m", "type": "lesson", "content": 42},
        {"memory_id": "m", "type": 42, "content": "text"},
    ],
)
def test_malformed_required_record_is_rejected_without_effect(tmp_path: Path, record: dict):
    store = MemoryStore(tmp_path)
    store.append(_valid())
    before_bytes = store.path.read_bytes()
    before_revision = store.revision()
    before_backup = store.backup_path.read_bytes()

    with pytest.raises(MemoryStoreRecordInvalid):
        store.append(record)

    assert store.path.read_bytes() == before_bytes
    assert store.revision() == before_revision
    assert store.backup_path.read_bytes() == before_backup


@pytest.mark.parametrize(
    "record",
    [
        _valid(status="unknown"),
        _valid(scope="unsupported"),
        _valid(scope="project"),
        _valid(scope="project", project_id=" "),
        _valid(scope="global", project_id="project-a"),
        _valid(project_id="project-a"),
        _valid(is_approved="yes"),
        _valid(related_notes="not-a-list"),
        _valid(timestamp=123),
    ],
)
def test_invalid_optional_lifecycle_scope_or_provenance_fields_are_rejected(tmp_path: Path, record: dict):
    with pytest.raises(MemoryStoreRecordInvalid):
        MemoryStore(tmp_path).append(record)
    assert not (tmp_path / ".claude" / "validated-memory.json").exists()


def test_valid_sparse_legacy_record_keeps_fields_and_revision(tmp_path: Path):
    record = _valid()
    persisted = MemoryStore(tmp_path).append(record)
    assert persisted["revision"] == 1
    assert persisted["validated_memory"] == [record]


def test_valid_scoped_records_preserve_scope_rules(tmp_path: Path):
    store = MemoryStore(tmp_path)
    store.append(_valid(memory_id="global", scope="global"))
    store.append(_valid(memory_id="project", scope="project", project_id="project-a"))
    records = store.load()["validated_memory"]
    assert records[0]["scope"] == "global"
    assert records[1]["project_id"] == "project-a"


def test_expected_revision_conflict_still_uses_existing_memory_store_error(tmp_path: Path):
    store = MemoryStore(tmp_path)
    store.append(_valid())
    with pytest.raises(MemoryStoreError) as error:
        store.append(_valid(memory_id="stale"), expected_revision=0)
    assert type(error.value).__name__ == "MemoryStoreConflict"
    assert store.revision() == 1


def test_package_legacy_and_bare_memory_store_keep_identity():
    legacy = importlib.import_module("memory_store")
    package = importlib.import_module("brain_eleven.memory.store")
    assert MemoryStore is legacy.MemoryStore is package.MemoryStore
    assert MemoryStoreRecordInvalid is legacy.MemoryStoreRecordInvalid is package.MemoryStoreRecordInvalid
