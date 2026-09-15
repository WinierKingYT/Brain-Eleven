"""Focused concurrency and failure evidence for the authority cache."""

from __future__ import annotations

import json
import multiprocessing
import threading
import time
from pathlib import Path

import pytest

import authority.cache as cache_module
from authority.cache import AuthorityCache
from authority.resolver import AuthorityResolver


def _store_from_process(vault: str, index: int, barrier, results) -> None:
    try:
        barrier.wait(timeout=15)
        AuthorityCache(vault).store(
            f"process-{index:02d}",
            {"memory": 7, "state": {"project-a": 2}},
            {"candidate_ids": [f"mem-{index:02d}"]},
        )
        results.put((index, "ok", ""))
    except Exception as exc:  # pragma: no cover - asserted by parent
        results.put((index, "error", repr(exc)))


def _run_process_stress(vault: Path, count: int = 16) -> list[tuple[int, str, str]]:
    context = multiprocessing.get_context("spawn")
    barrier = context.Barrier(count)
    results = context.Queue()
    processes = [
        context.Process(target=_store_from_process, args=(str(vault), index, barrier, results))
        for index in range(count)
    ]
    for process in processes:
        process.start()
    for process in processes:
        process.join(timeout=30)
    for process in processes:
        assert not process.is_alive()
        assert process.exitcode == 0
    return [results.get(timeout=5) for _ in processes]


def test_authority_cache_preserves_unique_process_writes(tmp_path):
    results = _run_process_stress(tmp_path)
    assert all(status == "ok" for _index, status, _detail in results), results
    payload = json.loads((tmp_path / ".claude" / "authority-cache.json").read_text(encoding="utf-8"))
    assert set(payload["entries"]) == {f"process-{index:02d}" for index in range(16)}


def test_authority_cache_access_refresh_is_atomic_for_raw_readers(tmp_path):
    cache = AuthorityCache(tmp_path)
    revisions = {"memory": 7, "state": {"project-a": 2}}
    reference = {"candidate_ids": ["mem-a"]}
    cache.store("seed", revisions, reference)
    stop = threading.Event()
    malformed: list[str] = []

    def refresh() -> None:
        while not stop.is_set():
            assert cache.load("seed", revisions) == reference

    def raw_reader() -> None:
        while not stop.is_set():
            try:
                json.loads(cache.path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                malformed.append(str(exc))
            except OSError:
                pass

    threads = [threading.Thread(target=refresh) for _ in range(4)]
    threads.append(threading.Thread(target=raw_reader))
    for thread in threads:
        thread.start()
    time.sleep(0.25)
    stop.set()
    for thread in threads:
        thread.join(timeout=10)
    assert not malformed
    assert cache.load("seed", revisions) == reference


def test_authority_cache_identity_remains_shared_with_resolver(tmp_path):
    resolver = AuthorityResolver(tmp_path)
    assert resolver.cache.__class__ is AuthorityCache
    assert cache_module.AuthorityCache is AuthorityCache


def test_authority_cache_lock_timeout_is_fail_open(tmp_path, monkeypatch):
    class FailingLock:
        def __enter__(self):
            raise TimeoutError("authority cache lock unavailable")

        def __exit__(self, *_args):
            return False

    monkeypatch.setattr(cache_module, "file_lock", lambda *_args, **_kwargs: FailingLock())
    cache = AuthorityCache(tmp_path)
    assert cache.load("missing", {"memory": 1}) is None
    cache.store("ignored", {"memory": 1}, {"candidate_ids": ["safe"]})
    assert not cache.path.exists()


def test_authority_cache_refresh_write_failure_preserves_valid_hit(tmp_path, monkeypatch):
    cache = AuthorityCache(tmp_path)
    revisions = {"memory": 1}
    reference = {"candidate_ids": ["safe"]}
    cache.store("key", revisions, reference)

    def fail_write(_document):
        raise OSError("refresh fsync failed")

    monkeypatch.setattr(cache, "_write_unlocked", fail_write)
    assert cache.load("key", revisions) == reference


@pytest.mark.parametrize("failure", ["fsync", "replace"])
def test_authority_cache_store_write_failure_has_no_canonical_effect(tmp_path, monkeypatch, failure):
    cache = AuthorityCache(tmp_path)
    if failure == "fsync":
        monkeypatch.setattr(cache_module.os, "fsync", lambda *_args: (_ for _ in ()).throw(OSError("fsync")))
    else:
        monkeypatch.setattr(Path, "replace", lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("replace")))

    with pytest.raises(OSError):
        cache.store("key", {"memory": 1}, {"candidate_ids": ["safe"]})
    if cache.path.exists():
        payload = json.loads(cache.path.read_text(encoding="utf-8"))
        assert "key" not in payload.get("entries", {})
    assert not list(cache.path.parent.glob(".authority-cache-*.json"))

