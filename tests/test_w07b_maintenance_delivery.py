"""W-07B native maintenance intent, freshness and privacy contract tests."""

from brain_eleven.memory import MemoryStore
from brain_eleven.projects.registry import ProjectRegistry
from brain_eleven.runtime import maintenance_delivery as delivery
from brain_eleven.runtime import maintenance
from brain_eleven.runtime.storage import RuntimeConfig, write_json
from brain_eleven.runtime.worker import Worker
from brain_eleven.state import StateStore
from scripts.capture_event import HookEvent
from scripts.capture_queue import CaptureQueue
import json
from pathlib import Path


def _vault(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    project = ProjectRegistry(vault).register(vault, proactive_capture=True)
    StateStore(vault).init_project(project["project_id"], source={"type": "user", "reference": "w07b"})
    return vault, project["project_id"]


def _job(project_id, *, event_type="SESSION_END"):
    return {
        "job_id": "cap_w07b_001",
        "event": {
            "event_type": event_type,
            "event_id": "event-w07b-001",
            "project": {"project_id": project_id, "status": "active"},
        },
    }


def _result():
    return {"status": "PROCESSED", "effect_verified": True, "canonical_effect_count": 1}


def _runtime_worker_vault(tmp_path):
    vault, project_id = _vault(tmp_path)
    write_json(RuntimeConfig(vault).path, {
        "schema_version": 1,
        "mode": "SHADOW",
        "project_ids": [project_id],
        "local_model": None,
    })
    event = HookEvent(
        event_id="event-worker-w07b",
        idempotency_key="capture-worker-w07b",
        event_type="SESSION_END",
        session_id="claude:worker-w07b",
        project_root=str(vault),
        project_id=project_id,
        project_status="resolved",
        event_at="2026-09-14T10:00:00Z",
    )
    CaptureQueue(vault).enqueue(event)
    return vault, project_id


def _raw_report():
    return {
        "graph": {"ok": True, "data": {"total_entities": 11, "total_relationships": 8,
            "projection": {"status": "fresh", "source_memory_revision": 0}}},
        "anomalies": {"ok": True, "data": {"total_memories_scanned": 4, "total_anomalies": 1,
            "by_severity": {"warning": 1}, "anomalies": [{"description": "private text"}]}},
        "digest": {"ok": True, "data": {"total_memories_considered": 3, "total_after_dedup": 2,
            "by_type": {"decision": [{"content": "private text"}]}}},
        "surface_at_next_session": True,
    }


def test_session_end_only_and_duplicate_intent_is_idempotent(tmp_path):
    vault, project_id = _vault(tmp_path)
    first = delivery.enqueue(vault, _job(project_id), _result())
    second = delivery.enqueue(vault, _job(project_id), _result())
    assert first["intent_id"] == second["intent_id"]
    assert len(list((delivery._root(vault) / "queued").glob("*.json"))) == 1
    assert delivery.enqueue(vault, _job(project_id, event_type="STOP"), _result()) is None


def test_worker_schedules_intent_only_after_terminal_capture(tmp_path, monkeypatch):
    vault, project_id = _runtime_worker_vault(tmp_path)
    worker = Worker(vault)

    def processed(job):
        checkpoint = worker._checkpoint_for(job)
        return {
            "status": "PROCESSED", "job_id": job["job_id"], "messages": 0,
            "effects": 0, "evidence_count": 0, "canonical_effect_count": 0,
            "review_effect_count": 0, "effect_ids": [],
            "canonical_operation_ids": [], "review_effect_ids": [],
            "effect_verified": True, "has_more": False,
            "checkpoint_key": checkpoint.name,
            "cursor": {"offset": 0, "prefix_hash": "0" * 64, "has_more": False},
        }

    monkeypatch.setattr(worker, "process", processed)
    result = worker.once()
    assert result["status"] == "PROCESSED"
    assert result["maintenance_intent_status"] == delivery.QUEUED
    queued = list((delivery._root(vault) / "queued").glob("*.json"))
    assert len(queued) == 1
    assert delivery.read_json(queued[0])["project_id"] == project_id


def test_completed_capture_reconciliation_recovers_enqueue_gap(tmp_path, monkeypatch):
    vault, project_id = _runtime_worker_vault(tmp_path)
    worker = Worker(vault)

    def processed(job):
        checkpoint = worker._checkpoint_for(job)
        return {
            "status": "PROCESSED", "job_id": job["job_id"], "messages": 0,
            "effects": 0, "evidence_count": 0, "canonical_effect_count": 0,
            "review_effect_count": 0, "effect_ids": [],
            "canonical_operation_ids": [], "review_effect_ids": [],
            "effect_verified": True, "has_more": False,
            "checkpoint_key": checkpoint.name,
            "cursor": {"offset": 0, "prefix_hash": "0" * 64, "has_more": False},
        }

    monkeypatch.setattr(worker, "process", processed)
    original_enqueue = delivery.enqueue
    monkeypatch.setattr(delivery, "enqueue", lambda *args, **kwargs: (_ for _ in ()).throw(OSError("outbox gap")))
    assert worker.once()["status"] == "PROCESSED"
    monkeypatch.setattr(delivery, "enqueue", original_enqueue)
    assert delivery.reconcile_completed(vault) == 1
    queued = list((delivery._root(vault) / "queued").glob("*.json"))
    assert len(queued) == 1
    assert delivery.read_json(queued[0])["project_id"] == project_id


def test_processing_publishes_privacy_safe_report_and_fresh_reminder(tmp_path, monkeypatch):
    vault, project_id = _vault(tmp_path)
    delivery.enqueue(vault, _job(project_id), _result())
    monkeypatch.setattr(maintenance, "run_maintenance", lambda *args, **kwargs: _raw_report())
    assert delivery.process_pending(vault) == 1
    reports = list((delivery._root(vault) / "reports").glob("*.json"))
    assert len(reports) == 1
    text = reports[0].read_text(encoding="utf-8")
    assert "private text" not in text
    assert "description" not in text
    reminder = delivery.latest_reminder(vault, project_id)
    assert reminder["status"] == "FRESH"
    assert "1 anomalies" in reminder["context"]


def test_published_report_replay_does_not_rerun_maintenance(tmp_path, monkeypatch):
    vault, project_id = _vault(tmp_path)
    delivery.enqueue(vault, _job(project_id), _result())
    calls = []

    def run_once(*args, **kwargs):
        calls.append(1)
        return _raw_report()

    monkeypatch.setattr(maintenance, "run_maintenance", run_once)
    assert delivery.process_pending(vault) == 1
    assert delivery.process_pending(vault) == 0
    assert len(calls) == 1


def test_crash_after_report_publication_resumes_without_rerun(tmp_path, monkeypatch):
    vault, project_id = _vault(tmp_path)
    delivery.enqueue(vault, _job(project_id), _result())
    original_write = delivery.write_json
    failed_once = {"value": False}

    def crash_before_terminal_move(path, value):
        if Path(path).parent.name == "completed" and not failed_once["value"]:
            failed_once["value"] = True
            raise RuntimeError("simulated terminal move crash")
        return original_write(path, value)

    monkeypatch.setattr(maintenance, "run_maintenance", lambda *args, **kwargs: _raw_report())
    monkeypatch.setattr(delivery, "write_json", crash_before_terminal_move)
    assert delivery.process_pending(vault) == 0
    assert list((delivery._root(vault) / "reports").glob("*.json"))

    rerun_calls = []
    monkeypatch.setattr(delivery, "write_json", original_write)
    monkeypatch.setattr(maintenance, "run_maintenance", lambda *args, **kwargs: rerun_calls.append(1))
    assert delivery.process_pending(vault) == 1
    assert rerun_calls == []
    assert len(list((delivery._root(vault) / "completed").glob("*.json"))) == 1


def test_crash_before_report_publication_promotes_staging_without_rerun(tmp_path, monkeypatch):
    vault, project_id = _vault(tmp_path)
    delivery.enqueue(vault, _job(project_id), _result())
    original_write = delivery.write_json
    failed_once = {"value": False}

    def crash_report_write(path, value):
        if Path(path).parent.name == "reports" and not failed_once["value"]:
            failed_once["value"] = True
            raise RuntimeError("simulated report publication crash")
        return original_write(path, value)

    monkeypatch.setattr(maintenance, "run_maintenance", lambda *args, **kwargs: _raw_report())
    monkeypatch.setattr(delivery, "write_json", crash_report_write)
    assert delivery.process_pending(vault) == 0
    assert list((delivery._root(vault) / "staging").glob("*.json"))

    rerun_calls = []
    monkeypatch.setattr(delivery, "write_json", original_write)
    monkeypatch.setattr(maintenance, "run_maintenance", lambda *args, **kwargs: rerun_calls.append(1))
    assert delivery.process_pending(vault) == 1
    assert rerun_calls == []


def test_revision_change_hides_old_report(tmp_path, monkeypatch):
    vault, project_id = _vault(tmp_path)
    delivery.enqueue(vault, _job(project_id), _result())
    monkeypatch.setattr(maintenance, "run_maintenance", lambda *args, **kwargs: _raw_report())
    assert delivery.process_pending(vault) == 1
    before = delivery.latest_reminder(vault, project_id)
    assert before["status"] == "FRESH"
    store = MemoryStore(vault)
    store.transact(lambda latest: latest["validated_memory"].append({
        "memory_id": "w07b-revision-bump", "content": "revision bump",
        "memory_type": "lesson", "scope": "project", "project_id": project_id,
        "status": "active", "confidence": 0.5,
    }) or None)
    assert delivery.latest_reminder(vault, project_id)["status"] == "STALE_OR_MISSING"


def test_corrupt_or_foreign_report_is_never_delivered(tmp_path):
    vault, project_id = _vault(tmp_path)
    root = delivery._root(vault)
    (root / "reports").mkdir(parents=True)
    (root / "reports" / "corrupt.json").write_text("{not json", encoding="utf-8")
    assert delivery.latest_reminder(vault, project_id)["status"] == "STALE_OR_MISSING"

    foreign = {
        "schema_version": delivery.SCHEMA_VERSION,
        "status": "SUCCESS",
        "intent_id": "foreign",
        "project_id": "other-project",
        "source_memory_revision": 0,
        "source_state_revision": 0,
    }
    (root / "reports" / "foreign.json").write_text(json.dumps(foreign), encoding="utf-8")
    assert delivery.latest_reminder(vault, project_id)["status"] == "STALE_OR_MISSING"


def test_surface_flag_and_delivery_receipt_bound_reminders(tmp_path, monkeypatch):
    vault, project_id = _vault(tmp_path)
    delivery.enqueue(vault, _job(project_id), _result())
    raw = _raw_report()
    raw["surface_at_next_session"] = False
    monkeypatch.setattr(maintenance, "run_maintenance", lambda *args, **kwargs: raw)
    assert delivery.process_pending(vault) == 1
    assert delivery.latest_reminder(vault, project_id, delivery_key="session-1")["status"] == "STALE_OR_MISSING"

    delivery.enqueue(vault, {**_job(project_id), "event": {**_job(project_id)["event"], "event_id": "event-w07b-002"}}, _result())
    raw["surface_at_next_session"] = True
    assert delivery.process_pending(vault) == 1
    fresh = delivery.latest_reminder(vault, project_id, delivery_key="session-1")
    assert fresh["status"] == "FRESH"
    assert delivery.ack_reminder(vault, project_id, fresh["report_id"], "session-1") is True
    assert delivery.latest_reminder(vault, project_id, delivery_key="session-1")["status"] == "ALREADY_DELIVERED"

def test_failed_delivery_is_bounded_and_content_free(tmp_path, monkeypatch):
    vault, project_id = _vault(tmp_path)
    delivery.enqueue(vault, _job(project_id), _result())
    before_memory = MemoryStore(vault).revision()
    before_state = StateStore(vault).project_revision(project_id)
    class UnsafeFailure(RuntimeError):
        code = "raw private exception"

    def fail(*args, **kwargs):
        raise UnsafeFailure("raw private exception")
    monkeypatch.setattr(maintenance, "run_maintenance", fail)
    assert delivery.process_pending(vault) == 0
    failed = list((delivery._root(vault) / "queued").glob("*.json"))
    assert len(failed) == 1
    for _ in range(2):
        delivery.process_pending(vault)
    failed = list((delivery._root(vault) / "failed").glob("*.json"))
    assert len(failed) == 1
    assert "raw private exception" not in failed[0].read_text(encoding="utf-8")
    assert "MAINTENANCE_FAILED" in failed[0].read_text(encoding="utf-8")
    assert MemoryStore(vault).revision() == before_memory
    assert StateStore(vault).project_revision(project_id) == before_state
