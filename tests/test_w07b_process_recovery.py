"""Process-level restart evidence for W-07B durable maintenance intents."""

from __future__ import annotations

import json
import multiprocessing
import os
from pathlib import Path

from brain_eleven.memory import MemoryStore
from brain_eleven.projects.registry import ProjectRegistry
from brain_eleven.runtime import maintenance, maintenance_delivery as delivery
from brain_eleven.runtime.storage import RuntimeConfig, write_json
from brain_eleven.state import StateStore


def _vault(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    project = ProjectRegistry(vault).register(vault, proactive_capture=True)
    StateStore(vault).init_project(project["project_id"], source={"type": "user", "reference": "w07b-process"})
    write_json(RuntimeConfig(vault).path, {
        "schema_version": 1,
        "mode": "SHADOW",
        "project_ids": [project["project_id"]],
        "local_model": None,
    })
    return vault, project["project_id"]


def _job(project_id):
    return {
        "job_id": "cap-w07b-process-001",
        "event": {
            "event_type": "SESSION_END",
            "event_id": "event-w07b-process-001",
            "project": {"project_id": project_id, "status": "active"},
        },
    }


def _raw_report():
    return {
        "graph": {"ok": True, "data": {"projection": {"source_memory_revision": 0}}},
        "anomalies": {"ok": True, "data": {"total_memories_scanned": 0,
            "total_anomalies": 0, "by_severity": {"warning": 0}}},
        "digest": {"ok": True, "data": {"total_memories_considered": 0,
            "total_after_dedup": 0}},
        "surface_at_next_session": True,
    }


def _crash_worker(vault: str, boundary: str, signal) -> None:
    """Run one child and terminate at a named durable boundary."""
    from brain_eleven.runtime import maintenance as child_maintenance
    from brain_eleven.runtime import maintenance_delivery as child_delivery

    child_maintenance.run_maintenance = lambda *args, **kwargs: _raw_report()
    if boundary == "claim":
        original = child_delivery.write_json

        def crash_after_claim(path, value):
            result = original(path, value)
            if Path(path).parent.name in {"queued", "processing"} and value.get("status") == "PROCESSING":
                signal.send("claim")
                os._exit(91)
            return result

        child_delivery.write_json = crash_after_claim
    elif boundary == "staging":
        original = child_delivery._owned_write

        def crash_after_staging(*args, **kwargs):
            result = original(*args, **kwargs)
            signal.send("staging")
            os._exit(92)
            return result  # pragma: no cover

        child_delivery._owned_write = crash_after_staging
    elif boundary == "publication":
        original = child_delivery.write_json

        def crash_before_terminal_move(path, value):
            if Path(path).parent.name == "completed" and value.get("status") == child_delivery.COMPLETED:
                signal.send("publication")
                os._exit(93)
            return original(path, value)

        child_delivery.write_json = crash_before_terminal_move
    child_delivery.process_pending(vault)
    signal.send("completed")


def _run_crash(vault: Path, boundary: str) -> None:
    context = multiprocessing.get_context("spawn")
    receive, send = context.Pipe(duplex=False)
    process = context.Process(target=_crash_worker, args=(str(vault), boundary, send))
    process.start()
    send.close()
    assert receive.poll(30), f"child did not reach {boundary} boundary"
    marker = receive.recv()
    process.join(timeout=30)
    assert not process.is_alive()
    if boundary == "claim":
        assert marker == "claim"
        assert process.exitcode == 91
    elif boundary == "staging":
        assert marker == "staging"
        assert process.exitcode == 92
    elif boundary == "publication":
        assert marker == "publication"
        assert process.exitcode == 93


def _expire_processing(vault: Path) -> None:
    for directory in ("queued", "processing"):
        for path in (delivery._root(vault) / directory).glob("*.json"):
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload["lease_expires_at"] = 0
            write_json(path, payload)


def test_process_restart_after_claim_recovers_one_report(tmp_path, monkeypatch):
    vault, project_id = _vault(tmp_path)
    delivery.enqueue(vault, _job(project_id), {"status": "PROCESSED", "effect_verified": True})
    _run_crash(vault, "claim")
    _expire_processing(vault)
    monkeypatch.setattr(maintenance, "run_maintenance", lambda *args, **kwargs: _raw_report())
    assert delivery.process_pending(vault) == 1
    assert len(list((delivery._root(vault) / "reports").glob("*.json"))) == 1
    assert len(list((delivery._root(vault) / "completed").glob("*.json"))) == 1


def test_process_restart_after_staging_promotes_without_rerun(tmp_path, monkeypatch):
    vault, project_id = _vault(tmp_path)
    delivery.enqueue(vault, _job(project_id), {"status": "PROCESSED", "effect_verified": True})
    _run_crash(vault, "staging")
    _expire_processing(vault)
    monkeypatch.setattr(maintenance, "run_maintenance", lambda *args, **kwargs: _raw_report())
    assert delivery.process_pending(vault) == 1
    assert len(list((delivery._root(vault) / "reports").glob("*.json"))) == 1
    assert not list((delivery._root(vault) / "staging").glob("*.json"))


def test_process_restart_after_publication_reconciles_without_rerun(tmp_path, monkeypatch):
    vault, project_id = _vault(tmp_path)
    delivery.enqueue(vault, _job(project_id), {"status": "PROCESSED", "effect_verified": True})
    _run_crash(vault, "publication")
    _expire_processing(vault)
    monkeypatch.setattr(maintenance, "run_maintenance", lambda *args, **kwargs: _raw_report())
    assert delivery.process_pending(vault) == 1
    assert len(list((delivery._root(vault) / "completed").glob("*.json"))) == 1


def test_restart_after_final_receipt_is_noop(tmp_path):
    vault, project_id = _vault(tmp_path)
    delivery.enqueue(vault, _job(project_id), {"status": "PROCESSED", "effect_verified": True})
    assert delivery.process_pending(vault) == 1
    assert delivery.process_pending(vault) == 0
    assert len(list((delivery._root(vault) / "reports").glob("*.json"))) == 1
    assert MemoryStore(vault).revision() == 0
