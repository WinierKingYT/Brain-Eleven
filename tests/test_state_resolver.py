"""Read-only Phase 16 StateResolver behavior tests."""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from project_registry import ProjectRegistry  # noqa: E402
from state_resolver import (  # noqa: E402
    PROJECT_ARCHIVED,
    PROJECT_UNKNOWN,
    STATE_AVAILABLE,
    STATE_CORRUPT,
    STATE_NOT_FOUND,
    StateResolver,
)
from state_store import StateService, StateStore  # noqa: E402


SOURCE = {"type": "user", "reference": "test"}
NOW = "2026-09-03T12:00:00Z"


def configured_state(tmp_path):
    registry = ProjectRegistry(tmp_path)
    registry.register(tmp_path / "brain-eleven", project_id="brain-eleven")
    service = StateService(tmp_path)
    service.init_project("brain-eleven", source=SOURCE, now=NOW)
    service.set_current_milestone(
        "brain-eleven",
        phase_id="phase-16",
        title="Task + State Model",
        expected_revision=1,
        source=SOURCE,
        record_id="mil_01J00000000000000000000000",
        now=NOW,
    )
    service.set_current_objective(
        "brain-eleven",
        text="Build a reliable Task + State model",
        expected_revision=2,
        source=SOURCE,
        record_id="obj_01J00000000000000000000000",
        now=NOW,
    )
    return registry, service


def test_resolver_returns_only_requested_current_project_state_and_stale_metadata(tmp_path):
    _registry, _service = configured_state(tmp_path)

    state = StateResolver(tmp_path).resolve(
        "brain-eleven",
        now=datetime(2026, 10, 4, tzinfo=timezone.utc),
    )

    assert state.status == STATE_AVAILABLE
    assert state.current["phase_id"] == "phase-16"
    assert state.current["objective"]["id"].startswith("obj_")
    assert state.freshness["status"] == "stale_candidate"
    assert state.references["wrong_project"] == []


def test_resolver_distinguishes_unknown_missing_corrupt_and_archived_state(tmp_path):
    registry = ProjectRegistry(tmp_path)
    registry.register(tmp_path / "brain-eleven", project_id="brain-eleven")
    resolver = StateResolver(tmp_path)
    assert resolver.resolve("unknown").status == PROJECT_UNKNOWN
    assert resolver.resolve("brain-eleven").status == STATE_NOT_FOUND

    store = StateStore(tmp_path)
    store.path.parent.mkdir(parents=True, exist_ok=True)
    store.path.write_text("{not valid json", encoding="utf-8")
    assert StateResolver(tmp_path).resolve("brain-eleven").status == STATE_CORRUPT

    archive_vault = tmp_path / "archive-vault"
    archive_root = archive_vault / "archived"
    registry = ProjectRegistry(archive_vault)
    registry.register(archive_root, project_id="archived")
    service = StateService(archive_vault)
    service.init_project("archived", source=SOURCE, now=NOW)
    registry.set_status("archived", "archived")
    assert StateResolver(archive_vault).resolve("archived").status == PROJECT_ARCHIVED
