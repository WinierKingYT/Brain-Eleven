"""SRT-01 regression tests for the runtime lock context-manager boundary."""

import threading

import pytest

from brain_eleven.runtime import storage


def _runtime_root(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    config = storage.RuntimeConfig(vault)
    config.ensure_root()
    return config.root


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
