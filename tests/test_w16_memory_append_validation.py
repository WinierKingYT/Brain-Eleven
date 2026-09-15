"""W-16 contract tests for the public canonical-memory append boundary."""

from pathlib import Path

import pytest

import memory_store as legacy_memory_store  # noqa: E402
from brain_eleven.memory import MemoryStore as PackageMemoryStore
from brain_eleven.memory.store import MemoryStore as PackageStoreMemoryStore


MemoryStore = legacy_memory_store.MemoryStore
MemoryStoreConflict = legacy_memory_store.MemoryStoreConflict
MemoryStoreError = legacy_memory_store.MemoryStoreError
# The production validator is intentionally outside this test-only step. The
# fallback keeps the red baseline executable before that bounded implementation
# lands, while a future stable subclass is picked up automatically.
MemoryStoreRecordInvalid = getattr(
    legacy_memory_store, "MemoryStoreRecordInvalid", MemoryStoreError
)


@pytest.fixture
def vault(tmp_path: Path) -> Path:
    (tmp_path / ".claude").mkdir(parents=True)
    return tmp_path


def _sparse(memory_id: str = "mem-sparse", **changes) -> dict:
    record = {
        "memory_id": memory_id,
        "type": "lesson",
        "content": "A minimally valid canonical memory.",
    }
    record.update(changes)
    return record


def _full(memory_id: str = "mem-full") -> dict:
    return {
        "memory_id": memory_id,
        "type": "decision",
        "content": "Use SQLite for the local runtime cache.",
        "status": "active",
        "scope": "project",
        "project_id": "project-a",
        "project": "PromtGen",
        "project_label": "PromtGen",
        "timestamp": "2026-09-15T10:00:00Z",
        "source_id": "session-001",
        "source": "user",
        "dedup_fingerprint": "a" * 64,
        "is_approved": False,
        "issues": [],
        "related_notes": [],
        "future_extension": {"version": 1},
    }


@pytest.mark.parametrize(
    "record",
    [
        None,
        [],
        "not-a-record",
        {},
        {"type": "lesson", "content": "missing identity"},
        {"memory_id": "m", "content": "missing type"},
        {"memory_id": "m", "type": "lesson"},
        _sparse(memory_id=""),
        _sparse(memory_id="   "),
        _sparse(type=""),
        _sparse(type="   "),
        _sparse(content=""),
        _sparse(content="   "),
        _sparse(memory_id=7),
        _sparse(type=7),
        _sparse(content=7),
    ],
)
def test_required_record_fields_are_rejected_without_effect(vault, record):
    store = MemoryStore(vault)
    store.append(_sparse("seed"))
    store.append(_sparse("second"))
    canonical_before = store.path.read_bytes()
    backup_before = store.backup_path.read_bytes()
    revision_before = store.revision()

    with pytest.raises(MemoryStoreRecordInvalid):
        store.append(record)

    assert store.path.read_bytes() == canonical_before
    assert store.backup_path.read_bytes() == backup_before
    assert store.revision() == revision_before
    assert {item["memory_id"] for item in store.load()["validated_memory"]} == {
        "seed",
        "second",
    }


@pytest.mark.parametrize(
    "record",
    [
        _sparse(status=" "),
        _sparse(status=None),
        _sparse(status=1),
        _sparse(scope="workspace"),
        _sparse(scope=None),
        _sparse(scope="global", project_id="project-a"),
        _sparse(scope="global", project="PromtGen"),
        _sparse(scope="global", project_label="PromtGen"),
        _sparse(scope="project"),
        _sparse(scope="project", project_id=""),
        _sparse(scope="project", project_id="   "),
        _sparse(timestamp=123),
        _sparse(source_id=123),
        _sparse(source={"type": "user"}),
        _sparse(dedup_fingerprint=123),
        _sparse(project=123),
        _sparse(project_label=123),
        _sparse(is_approved="false"),
        _sparse(issues={}),
        _sparse(related_notes={}),
        _sparse(project_id=123),
        _sparse(project_id="project-a"),
    ],
)
def test_lifecycle_optional_types_and_scope_metadata_are_rejected(vault, record):
    store = MemoryStore(vault)
    store.append(_sparse("seed"))
    canonical_before = store.path.read_bytes()
    backup_before = store.backup_path.read_bytes() if store.backup_path.exists() else None

    with pytest.raises(MemoryStoreRecordInvalid):
        store.append(record)

    assert store.path.read_bytes() == canonical_before
    assert (store.backup_path.read_bytes() if store.backup_path.exists() else None) == backup_before
    assert store.revision() == 1


def test_valid_sparse_and_full_records_preserve_values_and_transaction_parity(vault):
    store = MemoryStore(vault)
    sparse = _sparse("sparse")
    full = _full("full")

    first = store.append(sparse)
    second = store.append(full)

    assert first["revision"] == 1
    assert second["revision"] == 2
    assert second["validated_memory"] == [sparse, full]
    assert store.backup_path.exists()


def test_stale_expected_revision_rejects_valid_record_without_effect(vault):
    store = MemoryStore(vault)
    store.append(_sparse("seed"))
    canonical_before = store.path.read_bytes()
    backup_before = store.backup_path.read_bytes() if store.backup_path.exists() else None

    with pytest.raises(MemoryStoreConflict) as error:
        store.append(_sparse("stale"), expected_revision=0)

    assert error.value.expected_revision == 0
    assert error.value.actual_revision == 1
    assert store.path.read_bytes() == canonical_before
    assert (store.backup_path.read_bytes() if store.backup_path.exists() else None) == backup_before
    assert store.revision() == 1


def test_package_and_legacy_surfaces_preserve_memory_store_identity():
    assert PackageMemoryStore is PackageStoreMemoryStore is legacy_memory_store.MemoryStore


def test_record_invalid_error_is_a_stable_memory_store_error():
    assert issubclass(MemoryStoreRecordInvalid, MemoryStoreError)
    assert MemoryStoreRecordInvalid.__name__ == "MemoryStoreRecordInvalid"


def test_valid_global_record_has_no_project_identity(vault):
    store = MemoryStore(vault)
    record = _sparse("global", scope="global")
    persisted = store.append(record)
    assert persisted["validated_memory"] == [record]


def test_valid_project_record_requires_and_preserves_project_identity(vault):
    store = MemoryStore(vault)
    record = _sparse("project", scope="project", project_id="project-a")
    persisted = store.append(record)
    assert persisted["validated_memory"] == [record]
