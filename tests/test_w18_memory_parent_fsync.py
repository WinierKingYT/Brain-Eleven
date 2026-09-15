"""W-18 evidence for canonical MemoryStore parent-directory durability."""

import os
import stat
from pathlib import Path

import pytest

import memory_store
from brain_eleven.memory import MemoryStore as PackageMemoryStore


def _vault(tmp_path: Path) -> Path:
    vault = tmp_path / "vault"
    (vault / ".claude").mkdir(parents=True)
    return vault


def test_memory_store_surfaces_are_identity_preserving():
    assert memory_store.MemoryStore is PackageMemoryStore


@pytest.mark.skipif(os.name == "nt", reason="directory fsync is not supported on Windows")
def test_parent_directory_fsync_follows_replace(monkeypatch, tmp_path):
    vault = _vault(tmp_path)
    events = []
    original_fsync = memory_store.os.fsync
    original_open = memory_store.os.open
    original_close = memory_store.os.close
    original_replace = Path.replace

    def record_fsync(descriptor):
        events.append("fsync")
        return original_fsync(descriptor)

    def record_open(*args, **kwargs):
        events.append("open")
        return original_open(*args, **kwargs)

    def record_close(descriptor):
        events.append("close")
        return original_close(descriptor)

    def record_replace(path, target):
        events.append("replace")
        return original_replace(path, target)

    monkeypatch.setattr(memory_store.os, "fsync", record_fsync)
    monkeypatch.setattr(memory_store.os, "open", record_open)
    monkeypatch.setattr(memory_store.os, "close", record_close)
    monkeypatch.setattr(Path, "replace", record_replace)

    memory_store.MemoryStore(vault).append(
        {"memory_id": "m1", "type": "lesson", "content": "durable"}
    )

    replace_index = events.index("replace")
    assert events[replace_index + 1 : replace_index + 4] == ["open", "fsync", "close"]


@pytest.mark.skipif(os.name == "nt", reason="directory fsync is not supported on Windows")
def test_parent_directory_fsync_failure_is_visible_and_cleans_temp(monkeypatch, tmp_path):
    vault = _vault(tmp_path)
    store = memory_store.MemoryStore(vault)
    store.append({"memory_id": "m1", "type": "lesson", "content": "seed"})
    original_fsync = memory_store.os.fsync

    def fail_directory_fsync(descriptor):
        if stat.S_ISDIR(os.fstat(descriptor).st_mode):
            raise OSError("simulated parent directory fsync failure")
        return original_fsync(descriptor)

    monkeypatch.setattr(memory_store.os, "fsync", fail_directory_fsync)
    with pytest.raises(memory_store.MemoryStoreError, match="Cannot persist"):
        store.append({"memory_id": "m2", "type": "lesson", "content": "published"})

    assert not list((vault / ".claude").glob(".memory-store-*.json"))
    # The failure occurs after replace; the partial publication is visible and
    # must not be misreported as a rollback.
    assert {item["memory_id"] for item in store.load()["validated_memory"]} == {"m1", "m2"}


def test_windows_parent_directory_fsync_is_explicitly_skipped(monkeypatch, tmp_path):
    called = []

    def unexpected_open(*_args, **_kwargs):
        called.append("open")
        raise AssertionError("directory fsync must be skipped on Windows")

    monkeypatch.setattr(memory_store.os, "name", "nt")
    monkeypatch.setattr(memory_store.os, "open", unexpected_open)

    memory_store._fsync_parent_directory(_vault(tmp_path) / ".claude" / "validated-memory.json")

    assert called == []
