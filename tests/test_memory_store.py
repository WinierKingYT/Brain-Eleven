"""Transactional canonical-store tests."""

import json
import multiprocessing
import sys
import traceback
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


def _append_from_independent_process(vault_path, memory_id, ready, start, results):
    """Simulate an independently started canonical-store writer."""
    try:
        store = MemoryStore(vault_path)
        initial_revision = store.revision()
        ready.put(("ready", memory_id, initial_revision))
        if not start.wait(timeout=10):
            raise TimeoutError("test coordinator did not release concurrent writers")
        persisted = store.append({
            "memory_id": memory_id,
            "type": "lesson",
            "content": f"concurrent write {memory_id}",
        })
        results.put(("ok", memory_id, persisted["revision"]))
    except Exception:
        results.put(("error", memory_id, traceback.format_exc()))


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


def test_two_independent_process_writers_preserve_both_records(vault):
    """The lock/reload/write contract must prevent a real lost update."""
    context = multiprocessing.get_context("spawn")
    ready = context.Queue()
    start = context.Event()
    results = context.Queue()
    process_ids = ("writer-a", "writer-b")
    processes = [
        context.Process(
            target=_append_from_independent_process,
            args=(str(vault), memory_id, ready, start, results),
        )
        for memory_id in process_ids
    ]

    try:
        for process in processes:
            process.start()

        observed_initial_revisions = [ready.get(timeout=15) for _ in processes]
        assert {
            (status, initial_revision)
            for status, _memory_id, initial_revision in observed_initial_revisions
        } == {("ready", 0)}

        start.set()
        reports = [results.get(timeout=15) for _ in processes]
        for process in processes:
            process.join(timeout=15)

        assert all(process.exitcode == 0 for process in processes)
        assert {status for status, _memory_id, _result in reports} == {"ok"}, reports
        assert {revision for _status, _memory_id, revision in reports} == {1, 2}
    finally:
        start.set()
        for process in processes:
            if process.is_alive():
                process.terminate()
            process.join(timeout=5)
        ready.close()
        results.close()

    latest = MemoryStore(vault).load()
    assert latest["revision"] == 2
    assert {memory["memory_id"] for memory in latest["validated_memory"]} == set(process_ids)


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
