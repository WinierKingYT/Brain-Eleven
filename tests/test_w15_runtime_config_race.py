"""W-15 regression tests for linearizable runtime configuration writes."""

from __future__ import annotations

import threading
from pathlib import Path

import pytest

import brain_eleven.runtime.storage as storage
from brain_eleven.runtime.storage import RuntimeConfig, RuntimeConfigConflict, read_json, write_json


def _seed(vault: Path, **overrides):
    value = {
        "schema_version": 1,
        "mode": "OFF",
        "project_ids": [],
        "local_model": None,
        "b1_human_approval": False,
    }
    value.update(overrides)
    write_json(RuntimeConfig(vault).path, value)


def _run_thread(target):
    errors = []

    def runner():
        try:
            target()
        except BaseException as exc:  # assert the exact exception in the caller
            errors.append(exc)

    thread = threading.Thread(target=runner)
    thread.start()
    return thread, errors


def test_cross_field_approval_writer_rejects_stale_mode_snapshot(tmp_path):
    _seed(tmp_path)
    first = RuntimeConfig(tmp_path)
    second = RuntimeConfig(tmp_path)
    loaded = threading.Event()
    release = threading.Event()
    original_load = first.load

    def paused_load():
        value = original_load()
        loaded.set()
        assert release.wait(5)
        return value

    first.load = paused_load
    thread, errors = _run_thread(lambda: first.set_human_approval(True))
    assert loaded.wait(5)
    second.set_mode("SHADOW")
    release.set()
    thread.join(5)

    assert len(errors) == 1
    assert isinstance(errors[0], RuntimeConfigConflict)
    assert read_json(second.path)["mode"] == "SHADOW"
    assert read_json(second.path)["b1_human_approval"] is False


def test_cross_field_mode_writer_rejects_stale_approval_snapshot(tmp_path):
    _seed(tmp_path)
    first = RuntimeConfig(tmp_path)
    second = RuntimeConfig(tmp_path)
    loaded = threading.Event()
    release = threading.Event()
    original_load = first.load

    def paused_load():
        value = original_load()
        loaded.set()
        assert release.wait(5)
        return value

    first.load = paused_load
    thread, errors = _run_thread(lambda: first.set_mode("SHADOW"))
    assert loaded.wait(5)
    second.set_human_approval(True)
    release.set()
    thread.join(5)

    assert len(errors) == 1
    assert isinstance(errors[0], RuntimeConfigConflict)
    final = read_json(second.path)
    assert final["mode"] == "OFF"
    assert final["b1_human_approval"] is True


def test_same_field_contention_rejects_stale_writer(tmp_path):
    _seed(tmp_path)
    first = RuntimeConfig(tmp_path)
    second = RuntimeConfig(tmp_path)
    loaded = threading.Event()
    release = threading.Event()
    original_load = first.load

    def paused_load():
        value = original_load()
        loaded.set()
        assert release.wait(5)
        return value

    first.load = paused_load
    thread, errors = _run_thread(lambda: first.set_human_approval(True))
    assert loaded.wait(5)
    second.set_human_approval(True)
    release.set()
    thread.join(5)

    assert len(errors) == 1
    assert isinstance(errors[0], RuntimeConfigConflict)
    assert read_json(second.path)["b1_human_approval"] is True


def test_stale_canary_cannot_overwrite_intervening_off(tmp_path, monkeypatch):
    _seed(tmp_path, mode="SHADOW", project_ids=["project-1"])
    gate = threading.Event()
    release = threading.Event()

    class FakeMemoryStore:
        def __init__(self, _vault):
            pass

        def load(self):
            return {"schema_version": 3}

    class FakeStateStore:
        def __init__(self, _vault):
            pass

        def load(self):
            return {"schema_version": 2}

    monkeypatch.setattr("brain_eleven.memory.MemoryStore", FakeMemoryStore)
    monkeypatch.setattr("brain_eleven.state.StateStore", FakeStateStore)
    import evals.runtime_eval as runtime_eval

    def paused_run(_suite):
        gate.set()
        assert release.wait(5)
        return {"status": "PASS"}

    monkeypatch.setattr(runtime_eval, "run", paused_run)
    first = RuntimeConfig(tmp_path)
    second = RuntimeConfig(tmp_path)
    thread, errors = _run_thread(lambda: first.set_mode("CANARY"))
    assert gate.wait(5)
    second.set_mode("OFF")
    release.set()
    thread.join(5)

    assert len(errors) == 1
    assert isinstance(errors[0], RuntimeConfigConflict)
    assert read_json(second.path)["mode"] == "OFF"


def test_installer_config_update_preserves_concurrent_approval(tmp_path, monkeypatch):
    _seed(tmp_path)
    install_started = threading.Event()
    release_install = threading.Event()

    class FakeRegistry:
        def __init__(self, _vault):
            pass

        def resolve(self, _root):
            return {"project_id": "project-1", "status": "active"}

        def set_proactive_capture(self, _project_id, _enabled):
            return None

    class FakeStateStore:
        def __init__(self, _vault):
            pass

        def project_revision(self, _project_id):
            return 1

    monkeypatch.setattr("brain_eleven.projects.registry.ProjectRegistry", FakeRegistry)
    monkeypatch.setattr("brain_eleven.state.StateStore", FakeStateStore)
    import brain_eleven.runtime.migration as migration
    monkeypatch.setattr(migration, "migrate", lambda _vault: {"status": "MIGRATED"})

    original_mutate = RuntimeConfig._mutate_current

    def paused_mutate(self, mutate):
        install_started.set()
        assert release_install.wait(5)
        return original_mutate(self, mutate)

    monkeypatch.setattr(RuntimeConfig, "_mutate_current", paused_mutate)
    install_module = __import__("brain_eleven.runtime.install", fromlist=["install"])
    errors = []

    def run_install():
        try:
            install_module.install(tmp_path, home=tmp_path, clients=())
        except BaseException as exc:
            errors.append(exc)

    thread = threading.Thread(target=run_install)
    thread.start()
    assert install_started.wait(5)
    RuntimeConfig(tmp_path).set_human_approval(True)
    release_install.set()
    thread.join(5)

    assert errors == []
    final = RuntimeConfig(tmp_path).load()
    assert final["project_ids"] == ["project-1"]
    assert final["mode"] == "SHADOW"
    assert final["b1_human_approval"] is True


def test_lock_failure_leaves_config_unchanged(tmp_path, monkeypatch):
    _seed(tmp_path)
    before = read_json(RuntimeConfig(tmp_path).path)

    from brain_eleven.infrastructure.locking import MemoryStoreLockTimeout

    def fail_lock(*_args, **_kwargs):
        raise MemoryStoreLockTimeout("busy")

    monkeypatch.setattr(storage, "file_lock", fail_lock)
    with pytest.raises(MemoryStoreLockTimeout):
        RuntimeConfig(tmp_path).set_human_approval(True)

    assert read_json(RuntimeConfig(tmp_path).path) == before


def test_successful_updates_preserve_unrelated_fields(tmp_path):
    _seed(
        tmp_path,
        mode="SHADOW",
        project_ids=["project-1"],
        local_model={"url": "http://127.0.0.1:9", "model": "tiny"},
        retrieval_mode="W06B_TASK_AWARE",
    )
    cfg = RuntimeConfig(tmp_path)
    cfg.set_human_approval(True)
    cfg.set_mode("OFF")
    final = cfg.load()
    assert final["mode"] == "OFF"
    assert final["b1_human_approval"] is True
    assert final["project_ids"] == ["project-1"]
    assert final["local_model"] == {"url": "http://127.0.0.1:9", "model": "tiny"}
    assert final["retrieval_mode"] == "W06B_TASK_AWARE"
