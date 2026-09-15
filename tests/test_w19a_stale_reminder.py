"""W-19A newest-report authority and deterministic reminder tests."""

import os

from brain_eleven.memory import MemoryStore
from brain_eleven.projects.registry import ProjectRegistry
from brain_eleven.runtime import maintenance_delivery as delivery
from brain_eleven.runtime.storage import write_json
from brain_eleven.state import StateStore


def _vault(tmp_path, *, with_state=True):
    vault = tmp_path / "vault"
    vault.mkdir()
    project = ProjectRegistry(vault).register(vault, proactive_capture=True)
    if with_state:
        StateStore(vault).init_project(project["project_id"],
                                       source={"type": "user", "reference": "w19a"})
    return vault, project["project_id"]


def _report(vault, project_id, name, generated_at, *, surface=True, degraded=False,
            memory_revision=0, state_revision="current", report_id=None):
    delivery._ensure(vault)
    if state_revision == "current":
        state_revision = StateStore(vault).project_revision(project_id)
    intent_id = delivery.identity("maintenance_", name, project_id)
    intent = {
        "intent_id": intent_id,
        "event_id_hash": "0" * 64,
        "project_id": project_id,
        "source_memory_revision": memory_revision,
        "source_state_revision": state_revision,
    }
    raw = {
        "graph": {"ok": not degraded, "data": {"projection": {
            "source_memory_revision": memory_revision}}},
        "anomalies": {"ok": not degraded, "data": {
            "total_memories_scanned": 4, "total_anomalies": 1,
            "by_severity": {"warning": 1}}},
        "digest": {"ok": not degraded, "data": {
            "total_memories_considered": 3, "total_after_dedup": 2}},
        "surface_at_next_session": surface,
    }
    report = delivery._safe_report(raw, intent, memory_revision=memory_revision,
                                   state_revision=state_revision)
    report["generated_at"] = generated_at
    if report_id is not None:
        report["report_id"] = report_id
    path = delivery._root(vault) / "reports" / (name + ".json")
    write_json(path, report)
    return path, report


def test_newer_clean_report_suppresses_older_surfaced_report(tmp_path):
    vault, project_id = _vault(tmp_path)
    _report(vault, project_id, "old", "2026-09-15T09:00:00+00:00")
    _report(vault, project_id, "new", "2026-09-15T10:00:00+00:00", surface=False)

    reminder = delivery.latest_reminder(vault, project_id)

    assert reminder == {"status": "STALE_OR_MISSING", "context": "", "project_id": project_id}


def test_newer_degraded_report_suppresses_older_surfaced_report(tmp_path):
    vault, project_id = _vault(tmp_path)
    _report(vault, project_id, "old", "2026-09-15T09:00:00+00:00")
    _report(vault, project_id, "new", "2026-09-15T10:00:00+00:00", degraded=True)

    assert delivery.latest_reminder(vault, project_id)["status"] == "STALE_OR_MISSING"


def test_invalid_foreign_and_stale_reports_are_skipped(tmp_path):
    vault, project_id = _vault(tmp_path)
    _, current = _report(vault, project_id, "current", "2026-09-15T10:00:00+00:00")
    _report(vault, project_id, "stale", "2026-09-15T11:00:00+00:00", memory_revision=9)
    _report(vault, "foreign-project", "foreign", "2026-09-15T12:00:00+00:00")
    invalid_path = delivery._root(vault) / "reports" / "invalid-generated-at.json"
    invalid = dict(current, generated_at="not-a-timestamp")
    write_json(invalid_path, invalid)

    reminder = delivery.latest_reminder(vault, project_id)

    assert reminder["status"] == "FRESH"
    assert reminder["report_id"] == current["report_id"]


def test_equal_mtime_and_timestamp_use_report_id_tie_break(tmp_path):
    vault, project_id = _vault(tmp_path)
    timestamp = "2026-09-15T10:00:00+00:00"
    low_id = "maintenance_report_" + "0" * 64
    high_id = "maintenance_report_" + "f" * 64
    low_path, _ = _report(vault, project_id, "low", timestamp, surface=False, report_id=low_id)
    high_path, _ = _report(vault, project_id, "high", timestamp, report_id=high_id)
    equal_mtime = 1_800_000_000
    os.utime(low_path, (equal_mtime, equal_mtime))
    os.utime(high_path, (equal_mtime, equal_mtime))

    first = delivery.latest_reminder(vault, project_id)
    second = delivery.latest_reminder(vault, project_id)

    assert first["status"] == second["status"] == "FRESH"
    assert first["report_id"] == second["report_id"] == high_id


def test_state_less_project_does_not_match_concrete_state_report(tmp_path):
    vault, project_id = _vault(tmp_path, with_state=False)
    _report(vault, project_id, "concrete-state", "2026-09-15T10:00:00+00:00", state_revision=0)

    assert delivery.latest_reminder(vault, project_id)["status"] == "STALE_OR_MISSING"


def test_latest_reminder_is_read_only_for_canonical_revisions(tmp_path):
    vault, project_id = _vault(tmp_path)
    _report(vault, project_id, "current", "2026-09-15T10:00:00+00:00")
    before_memory = MemoryStore(vault).revision()
    before_state = StateStore(vault).project_revision(project_id)

    delivery.latest_reminder(vault, project_id)

    assert MemoryStore(vault).revision() == before_memory
    assert StateStore(vault).project_revision(project_id) == before_state
