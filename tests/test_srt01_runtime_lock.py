"""SRT-01 regression tests for the runtime lock context-manager boundary."""

import multiprocessing
import threading

import pytest

from brain_eleven.runtime import storage
from brain_eleven.infrastructure.locking import MemoryStoreLockTimeout


def _runtime_root(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    config = storage.RuntimeConfig(vault)
    config.ensure_root()
    return config.root


def _hold_runtime_lock(target, entered, release, failed):
    try:
        with storage.runtime_file_lock(target):
            entered.set()
            release.wait(10)
    except BaseException:  # pragma: no cover - child reports through the event
        failed.set()


def test_runtime_file_lock_enters_and_releases_for_reuse(tmp_path):
    root = _runtime_root(tmp_path)
    target = root / "locks" / "single"
    entered = []

    with storage.runtime_file_lock(target):
        entered.append(True)

    with storage.runtime_file_lock(target):
        entered.append(True)

    assert entered == [True, True]
    assert not target.with_name(target.name + ".lock").exists()


def test_runtime_file_lock_releases_after_body_exception(tmp_path):
    root = _runtime_root(tmp_path)
    target = root / "locks" / "exception"

    with pytest.raises(RuntimeError, match="body failure"):
        with storage.runtime_file_lock(target):
            raise RuntimeError("body failure")

    with storage.runtime_file_lock(target):
        pass


def test_runtime_file_lock_timeout_releases_os_resources(tmp_path):
    root = _runtime_root(tmp_path)
    target = root / "locks" / "timeout"
    context = multiprocessing.get_context("spawn")
    entered = context.Event()
    release = context.Event()
    failed = context.Event()
    holder = context.Process(target=_hold_runtime_lock, args=(target, entered, release, failed))
    holder.start()
    try:
        assert entered.wait(10)
        with pytest.raises(MemoryStoreLockTimeout, match="Timed out acquiring runtime lock"):
            with storage.runtime_file_lock(target, timeout=0.2, poll_interval=0.01):
                raise AssertionError("timed acquisition unexpectedly entered")
    finally:
        release.set()
        holder.join(10)
        if holder.is_alive():
            holder.terminate()
            holder.join(5)

    assert holder.exitcode == 0
    assert not failed.is_set()
    with storage.runtime_file_lock(target):
        pass


def test_runtime_file_lock_releases_after_post_acquisition_validation_failure(tmp_path, monkeypatch):
    root = _runtime_root(tmp_path)
    target = root / "locks" / "post-acquisition"
    original_check = storage.assert_runtime_snapshot
    calls = []

    def fail_after_acquisition(runtime_root, path, snapshot):
        calls.append(True)
        if len(calls) == 2:
            raise storage.RuntimePathError("synthetic post-acquisition validation failure")
        return original_check(runtime_root, path, snapshot)

    with monkeypatch.context() as patch:
        patch.setattr(storage, "assert_runtime_snapshot", fail_after_acquisition)
        with pytest.raises(storage.RuntimePathError, match="post-acquisition validation failure"):
            with storage.runtime_file_lock(target):
                raise AssertionError("post-acquisition validation unexpectedly passed")

    assert len(calls) == 2
    with storage.runtime_file_lock(target):
        pass


def test_distinct_runtime_targets_can_enter_concurrently(tmp_path):
    root = _runtime_root(tmp_path)
    first = root / "locks" / "first"
    second = root / "locks" / "second"
    first_entered = threading.Event()
    release_first = threading.Event()
    second_entered = threading.Event()
    errors = []

    def hold_first():
        try:
            with storage.runtime_file_lock(first):
                first_entered.set()
                release_first.wait(5)
        except BaseException as exc:  # pragma: no cover - assertion below reports it
            errors.append(exc)

    thread = threading.Thread(target=hold_first)
    thread.start()
    try:
        assert first_entered.wait(5)
        with storage.runtime_file_lock(second):
            second_entered.set()
    finally:
        release_first.set()
        thread.join(5)

    assert errors == []
    assert second_entered.is_set()
    assert not thread.is_alive()
