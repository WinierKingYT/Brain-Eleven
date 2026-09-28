from brain_eleven.memory.store import MemoryStore
from brain_eleven.projects.registry import ProjectRegistry
from brain_eleven.runtime import maintenance, maintenance_delivery as delivery
from brain_eleven.state.store import StateStore
from evals.w07b.dogfood import _exercise_failed_retry


def test_dogfood_records_safe_failure_and_retry_for_session_end_intent(tmp_path, monkeypatch):
    vault = tmp_path / "vault"
    vault.mkdir()
    project = ProjectRegistry(vault).register(vault, proactive_capture=True)
    project_id = project["project_id"]
    StateStore(vault).init_project(project_id, source={"type": "user", "reference": "dogfood"})

    job = {
        "job_id": "cap_dogfood_001",
        "event": {
            "event_type": "SESSION_END",
            "event_id": "event-dogfood-001",
            "project": {"project_id": project_id, "status": "active"},
        },
    }
    result = {"status": "PROCESSED", "effect_verified": True, "canonical_effect_count": 1}
    assert delivery.enqueue(vault, job, result)

    def run_maintenance(vault_path, generated_by_run=None, project_id=None):
        revision = MemoryStore(vault_path).revision()
        return {
            "graph": {"ok": True, "data": {"total_entities": 1, "total_relationships": 0,
                "projection": {"status": "fresh", "source_memory_revision": revision}}},
            "anomalies": {"ok": True, "data": {"total_memories_scanned": 0,
                "total_anomalies": 0, "by_severity": {}, "anomalies": []}},
            "digest": {"ok": True, "data": {"total_memories_considered": 0,
                "total_after_dedup": 0, "by_type": {}}},
            "surface_at_next_session": False,
        }

    monkeypatch.setattr(maintenance, "run_maintenance", run_maintenance)
    report = _exercise_failed_retry(vault)

    assert report["verified"] is True
    assert report["status_after_failure"] == delivery.QUEUED
    assert report["attempt_after_failure"] == 1
    assert report["status_after_retry"] == delivery.COMPLETED
    assert report["attempt_after_retry"] == 2
    assert report["report_present"] is True
    assert report["canonical_unchanged_after_failure"] is True
    assert report["canonical_unchanged_after_retry"] is True
    assert report["memory_revision_before"] == report["memory_revision_after_failure"]
    assert report["state_revision_before"] == report["state_revision_after_failure"]
    assert report["project_registry_revision_before"] == report["project_registry_revision_after_failure"]
    assert "vault" not in report
