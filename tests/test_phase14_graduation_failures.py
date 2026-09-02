"""Failure-injection graduation tests for the memory foundation."""

import importlib.util
import json
import multiprocessing
import os
import sys
import traceback
from pathlib import Path

import pytest


SCRIPTS = Path(__file__).parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

import memory_store as memory_store_module  # noqa: E402
from entity_extractor import EntityExtractor  # noqa: E402
from knowledge_graph import KnowledgeGraph  # noqa: E402
from memory_store import (  # noqa: E402
    MemoryStore,
    MemoryStoreCorrupt,
    MemoryStoreError,
)
from memory_store_lock import MemoryStoreLockTimeout, memory_store_lock  # noqa: E402
from project_registry import ProjectRegistry, ProjectRegistryError  # noqa: E402


def _append_from_process(vault_path, memory_id, ready, start, results):
    try:
        store = MemoryStore(vault_path)
        ready.put(("ready", memory_id, store.revision()))
        if not start.wait(timeout=20):
            raise TimeoutError("test coordinator did not release writers")
        persisted = store.append({
            "memory_id": memory_id,
            "type": "lesson",
            "content": f"graduation write {memory_id}",
        })
        results.put(("ok", memory_id, persisted["revision"]))
    except Exception:
        results.put(("error", memory_id, traceback.format_exc()))


def _hold_store_lock(vault_path, locked, release):
    with memory_store_lock(vault_path, timeout=10):
        locked.put("locked")
        release.wait(timeout=20)


def _crash_while_holding_store_lock(vault_path, locked):
    with memory_store_lock(vault_path, timeout=10):
        locked.set()
        os._exit(17)


def _load_context_compiler():
    spec = importlib.util.spec_from_file_location(
        "phase14_graduation_context_compiler", SCRIPTS / "context-compiler.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.ContextCompiler


def _memory(memory_id, content="Use atomic writes"):
    return {
        "memory_id": memory_id,
        "type": "decision",
        "content": content,
        "confidence": 0.9,
        "quality_score": 0.9,
        "timestamp": "2026-09-02T12:00:00Z",
        "status": "active",
        "is_approved": True,
    }


@pytest.fixture
def vault(tmp_path):
    path = tmp_path / "vault"
    (path / ".claude").mkdir(parents=True)
    return path


@pytest.mark.parametrize(
    "payload, expected_error",
    [
        (b'{"validated_memory": [', "Cannot read canonical memory store"),
        (b'{"schema_version": 999, "validated_memory": []}', "Unsupported canonical schema"),
    ],
)
def test_invalid_canonical_input_hard_fails_without_becoming_empty(vault, payload, expected_error):
    path = vault / ".claude" / "validated-memory.json"
    path.write_bytes(payload)

    with pytest.raises(MemoryStoreCorrupt, match=expected_error):
        MemoryStore(vault).load()

    assert path.read_bytes() == payload


def test_corrupt_project_registry_fails_closed_without_rewriting(vault):
    path = vault / ".claude" / "project-registry.json"
    payload = b"{not-json"
    path.write_bytes(payload)

    with pytest.raises(ProjectRegistryError, match="Cannot read project registry"):
        ProjectRegistry(vault).list_projects()

    assert path.read_bytes() == payload


def test_invalid_mutation_and_tempfile_permission_error_preserve_canonical(vault, monkeypatch):
    store = MemoryStore(vault)
    store.append(_memory("stable"))
    canonical = store.path
    before = canonical.read_bytes()

    def invalid_mutation(data):
        data["validated_memory"] = "not-a-list"

    with pytest.raises(MemoryStoreCorrupt, match="bucket is not a list"):
        store.transact(invalid_mutation)
    assert canonical.read_bytes() == before

    def permission_denied(*_args, **_kwargs):
        raise PermissionError("simulated permission denied")

    monkeypatch.setattr(memory_store_module.tempfile, "mkstemp", permission_denied)
    with pytest.raises(MemoryStoreError, match="Cannot persist canonical memory store"):
        store.append(_memory("must-not-persist"))
    assert canonical.read_bytes() == before
    assert [memory["memory_id"] for memory in store.load()["validated_memory"]] == ["stable"]


def test_ten_parallel_writers_and_twenty_reopened_transactions_have_no_lost_updates(vault):
    context = multiprocessing.get_context("spawn")
    ready = context.Queue()
    start = context.Event()
    results = context.Queue()
    parallel_ids = [f"parallel-{index}" for index in range(10)]
    processes = [
        context.Process(
            target=_append_from_process,
            args=(str(vault), memory_id, ready, start, results),
        )
        for memory_id in parallel_ids
    ]

    try:
        for process in processes:
            process.start()
        observed = [ready.get(timeout=30) for _ in processes]
        assert {(status, revision) for status, _memory_id, revision in observed} == {("ready", 0)}
        start.set()
        reports = [results.get(timeout=30) for _ in processes]
        for process in processes:
            process.join(timeout=30)
        assert all(process.exitcode == 0 for process in processes)
        assert {status for status, _memory_id, _result in reports} == {"ok"}, reports
        assert {revision for _status, _memory_id, revision in reports} == set(range(1, 11))
    finally:
        start.set()
        for process in processes:
            if process.is_alive():
                process.terminate()
            process.join(timeout=5)
        ready.close()
        results.close()

    store = MemoryStore(vault)
    sequential_ids = [f"sequential-{index}" for index in range(20)]
    for memory_id in sequential_ids:
        MemoryStore(vault).append(_memory(memory_id))

    latest = store.load()
    assert latest["revision"] == 30
    assert {memory["memory_id"] for memory in latest["validated_memory"]} == set(
        parallel_ids + sequential_ids
    )


def test_lock_timeout_is_explicit_and_crashed_writer_releases_the_os_lock(vault):
    context = multiprocessing.get_context("spawn")
    locked = context.Queue()
    release = context.Event()
    holder = context.Process(target=_hold_store_lock, args=(str(vault), locked, release))
    holder.start()
    try:
        assert locked.get(timeout=20) == "locked"
        with pytest.raises(MemoryStoreLockTimeout):
            with memory_store_lock(vault, timeout=0.15, poll_interval=0.01):
                pass
    finally:
        release.set()
        holder.join(timeout=20)
        if holder.is_alive():
            holder.terminate()
            holder.join(timeout=5)
        locked.close()

    crashed_lock = context.Event()
    crashed = context.Process(
        target=_crash_while_holding_store_lock, args=(str(vault), crashed_lock)
    )
    crashed.start()
    try:
        assert crashed_lock.wait(timeout=20)
        crashed.join(timeout=20)
        assert crashed.exitcode == 17
        persisted = MemoryStore(vault).append(_memory("after-crash"))
    finally:
        if crashed.is_alive():
            crashed.terminate()
            crashed.join(timeout=5)

    assert persisted["revision"] == 1
    assert MemoryStore(vault).load()["validated_memory"][0]["memory_id"] == "after-crash"


def test_missing_or_corrupt_derived_state_is_rebuilt_and_stale_or_foreign_context_is_rejected(vault):
    store = MemoryStore(vault)
    store.append(_memory("m1"))
    graph_path = vault / ".claude" / "knowledge-graph.json"
    assert not graph_path.exists()

    fresh_graph = EntityExtractor(str(vault)).build_graph()
    assert fresh_graph.projection_status()["status"] == "fresh"
    graph_path.write_text("{broken graph", encoding="utf-8")
    assert KnowledgeGraph(str(vault)).projection_status()["status"] == "corrupt"
    assert EntityExtractor(str(vault)).build_graph().projection_status()["status"] == "fresh"

    ContextCompiler = _load_context_compiler()
    compiler = ContextCompiler(str(vault), project_id="project-a")
    compiler.save()
    assert ContextCompiler(str(vault), project_id="project-b").bootstrap_status()["status"] == "scope_mismatch"

    store.append(_memory("m2", "A newer canonical decision"))
    assert ContextCompiler(str(vault), project_id="project-a").bootstrap_status()["status"] == "stale"
    refreshed = ContextCompiler(str(vault), project_id="project-a")
    refreshed.save()
    assert refreshed.bootstrap_status()["status"] == "fresh"
