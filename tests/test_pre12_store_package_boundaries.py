from __future__ import annotations

import json
from pathlib import Path

from brain_eleven.memory import (
    CANONICAL_SCHEMA_VERSION,
    MemoryStore,
    MemoryStoreConflict,
    MemoryStoreCorrupt,
    MemoryStoreError,
)
from brain_eleven.memory.store import MemoryStore as PackagedMemoryStore
from brain_eleven.state import (
    STATE_FILENAME,
    STATE_SCHEMA_VERSION,
    StateStore,
    StateStoreConflict,
    StateStoreCorrupt,
    empty_project_state,
    empty_state_document,
    state_store_path,
    validate_state_document,
)
from brain_eleven.state.store import StateStore as PackagedStateStore

from memory_store import (
    CANONICAL_SCHEMA_VERSION as LEGACY_MEMORY_SCHEMA_VERSION,
    MemoryStore as LegacyMemoryStore,
    MemoryStoreConflict as LegacyMemoryStoreConflict,
    MemoryStoreCorrupt as LegacyMemoryStoreCorrupt,
    MemoryStoreError as LegacyMemoryStoreError,
)
from state_store import (
    STATE_FILENAME as LEGACY_STATE_FILENAME,
    STATE_SCHEMA_VERSION as LEGACY_STATE_SCHEMA_VERSION,
    StateStore as LegacyStateStore,
    StateStoreConflict as LegacyStateStoreConflict,
    StateStoreCorrupt as LegacyStateStoreCorrupt,
)


def test_memory_package_is_the_legacy_authority() -> None:
    assert MemoryStore is LegacyMemoryStore is PackagedMemoryStore
    assert MemoryStoreConflict is LegacyMemoryStoreConflict
    assert MemoryStoreCorrupt is LegacyMemoryStoreCorrupt
    assert MemoryStoreError is LegacyMemoryStoreError
    assert CANONICAL_SCHEMA_VERSION == LEGACY_MEMORY_SCHEMA_VERSION


def test_memory_package_preserves_load_and_revision_behavior(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path)
    snapshot = store.load()

    assert snapshot["schema_version"] == CANONICAL_SCHEMA_VERSION
    assert snapshot["revision"] == 0
    assert store.revision() == 0

    store.append({"memory_id": "mem_package_boundary", "type": "lesson"})
    persisted = json.loads(
        (tmp_path / ".claude" / "validated-memory.json").read_text(encoding="utf-8")
    )
    assert persisted["revision"] == 1
    assert persisted["validated_memory"][0]["memory_id"] == "mem_package_boundary"


def test_state_package_is_the_legacy_authority() -> None:
    assert StateStore is LegacyStateStore is PackagedStateStore
    assert StateStoreConflict is LegacyStateStoreConflict
    assert StateStoreCorrupt is LegacyStateStoreCorrupt
    assert STATE_FILENAME == LEGACY_STATE_FILENAME
    assert STATE_SCHEMA_VERSION == LEGACY_STATE_SCHEMA_VERSION


def test_state_package_preserves_schema_and_path_contract(tmp_path: Path) -> None:
    document = empty_state_document()
    validate_state_document(document)
    project = empty_project_state("project-boundary", {"type": "user"})

    assert document["schema_version"] == STATE_SCHEMA_VERSION
    assert project["project_id"] == "project-boundary"
    assert state_store_path(tmp_path) == tmp_path / ".claude" / STATE_FILENAME
    loaded = StateStore(tmp_path).load()
    assert loaded["schema_version"] == STATE_SCHEMA_VERSION
    assert loaded["store_revision"] == 0
    validate_state_document(loaded)
