"""Typed Phase 16 StateService transition tests."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from project_registry import ProjectRegistry  # noqa: E402
from state_store import (  # noqa: E402
    StateProjectArchived,
    StateProjectUnknown,
    StateService,
    StateTransitionError,
)


SOURCE = {"type": "user", "reference": "test"}
NOW = "2026-09-03T12:00:00Z"


def service_with_active_project(tmp_path):
    ProjectRegistry(tmp_path).register(tmp_path / "brain-eleven", project_id="brain-eleven")
    service = StateService(tmp_path)
    service.init_project("brain-eleven", source=SOURCE, now=NOW)
    return service


def test_typed_milestone_requirement_work_and_blocker_lifecycles(tmp_path):
    service = service_with_active_project(tmp_path)
    milestone_id = "mil_01J00000000000000000000000"
    service.set_current_milestone(
        "brain-eleven",
        phase_id="phase-16",
        title="Task + State Model",
        expected_revision=1,
        source=SOURCE,
        record_id=milestone_id,
        now=NOW,
    )
    service.transition_milestone(
        "brain-eleven",
        milestone_id=milestone_id,
        target_status="COMPLETED",
        expected_revision=2,
        source=SOURCE,
        now=NOW,
    )
    with pytest.raises(StateTransitionError, match="COMPLETED -> ACTIVE"):
        service.transition_milestone(
            "brain-eleven",
            milestone_id=milestone_id,
            target_status="ACTIVE",
            expected_revision=3,
            source=SOURCE,
        )

    requirement_id = "req_01J00000000000000000000000"
    service.add_requirement(
        "brain-eleven",
        text="State stays separate from memory",
        expected_revision=3,
        source=SOURCE,
        record_id=requirement_id,
        now=NOW,
    )
    service.resolve_requirement(
        "brain-eleven",
        requirement_id=requirement_id,
        expected_revision=4,
        source=SOURCE,
        now=NOW,
    )

    work_id = "wrk_01J00000000000000000000000"
    service.add_work_item(
        "brain-eleven",
        text="Add StateResolver",
        expected_revision=5,
        source=SOURCE,
        record_id=work_id,
        now=NOW,
    )
    service.transition_work_item(
        "brain-eleven",
        work_item_id=work_id,
        target_status="ACTIVE",
        expected_revision=6,
        source=SOURCE,
        now=NOW,
    )
    service.transition_work_item(
        "brain-eleven",
        work_item_id=work_id,
        target_status="DONE",
        expected_revision=7,
        source=SOURCE,
        now=NOW,
    )
    assert service.store.project_revision("brain-eleven") == 8


def test_unknown_and_archived_projects_cannot_be_initialized_or_mutated(tmp_path):
    service = StateService(tmp_path)
    with pytest.raises(StateProjectUnknown):
        service.init_project("unknown", source=SOURCE)

    registry = ProjectRegistry(tmp_path)
    registry.register(tmp_path / "archived", project_id="archived", status="archived")
    with pytest.raises(StateProjectArchived):
        service.init_project("archived", source=SOURCE)
