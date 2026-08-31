"""Transactional canonical-store tests."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from memory_store import (  # noqa: E402
    CANONICAL_SCHEMA_VERSION,
    MemoryStore,
    MemoryStoreConflict,
)


@pytest.fixture
def vault(tmp_path):
    vault = tmp_path / "vault"
    (vault / ".claude").mkdir(parents=True)
    return vault


def test_legacy_document_loads_as_revision_zero_without_rewriting(vault):
    path = vault / ".claude" / "validated-memory.json"
    legacy = {"validated_memory": [], "rejected_memory": [], "summary": {}}
    path.write_text(json.dumps(legacy), encoding="utf-8")

    store = MemoryStore(vault)
    loaded = store.load()

    assert loaded["schema_version"] == CANONICAL_SCHEMA_VERSION
    assert loaded["revision"] == 0
    assert json.loads(path.read_text(encoding="utf-8")) == legacy


def test_transaction_increments_revision_and_creates_backup(vault):
    store = MemoryStore(vault)
    first = store.append({"memory_id": "m1", "type": "lesson", "content": "one"})
    second = store.append({"memory_id": "m2", "type": "lesson", "content": "two"})

    assert first["revision"] == 1
    assert second["revision"] == 2
    assert [m["memory_id"] for m in second["validated_memory"]] == ["m1", "m2"]
    assert store.backup_path.exists()


def test_expected_revision_rejects_stale_writer_without_mutation(vault):
    store = MemoryStore(vault)
    store.append({"memory_id": "m1"})

    with pytest.raises(MemoryStoreConflict) as error:
        store.append({"memory_id": "m2"}, expected_revision=0)

    assert error.value.expected_revision == 0
    assert error.value.actual_revision == 1
    latest = store.load()
    assert latest["revision"] == 1
    assert [m["memory_id"] for m in latest["validated_memory"]] == ["m1"]


def test_corrupt_store_is_not_treated_as_empty(vault):
    path = vault / ".claude" / "validated-memory.json"
    path.write_text("{not-json", encoding="utf-8")

    from memory_store import MemoryStoreCorrupt

    with pytest.raises(MemoryStoreCorrupt):
        MemoryStore(vault).load()
