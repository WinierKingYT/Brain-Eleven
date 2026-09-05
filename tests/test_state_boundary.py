"""PRE-07 State/Memory boundary contract tests."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from extraction import NewMemoryCandidate, StateMutationProposal  # noqa: E402
from project_registry import ProjectRegistry  # noqa: E402
from state_boundary import BoundaryStatus, StateBoundary  # noqa: E402
from state_store import StateService  # noqa: E402


SOURCE = {"type": "user", "reference": "test"}


def _setup(tmp_path):
    project_root = tmp_path / "brain-eleven"
    registry = ProjectRegistry(tmp_path)
    registry.register(project_root, project_id="brain-eleven")
    service = StateService(tmp_path)
    service.init_project("brain-eleven", source=SOURCE, now="2026-09-05T10:00:00Z")
    return service, project_root


def _proposal(operation="ADD_BLOCKER", *, project_id="brain-eleven", commitment="OBSERVED"):
    return StateMutationProposal(
        candidate_id="cand_state_01",
        candidate_type="STATE_MUTATION",
        project_id=project_id,
        commitment=commitment,
        occurred_at=None,
        confidence=0.94,
        evidence_refs=("evd_01",),
        operation=operation,
        text="Authentication tests are failing.",
    )


def test_blocker_routes_to_state_without_memory_write(tmp_path):
    service, _ = _setup(tmp_path)
    before_memory = service.memory_store.load()
    result = StateBoundary(tmp_path).apply(_proposal(), expected_revision=1, source=SOURCE, commit=True, now="2026-09-05T10:01:00Z")

    assert result.status == BoundaryStatus.SUCCESS.value
    assert result.canonical_write is True
    assert service.store.get_project("brain-eleven")["blockers"][0]["text"] == "Authentication tests are failing."
    assert service.memory_store.load() == before_memory


def test_memory_candidate_is_skipped_and_decision_is_not_written_to_state(tmp_path):
    service, _ = _setup(tmp_path)
    candidate = NewMemoryCandidate(
        candidate_id="cand_memory_01",
        candidate_type="NEW_MEMORY",
        project_id="brain-eleven",
        commitment="COMMITTED",
        occurred_at=None,
        confidence=0.97,
        evidence_refs=("evd_01",),
        memory_type="decision",
        scope="project",
        content="SQLite will provide local persistence.",
    )
    result = StateBoundary(tmp_path).apply(candidate, expected_revision=1, commit=True)

    assert result.status == BoundaryStatus.SKIPPED.value
    assert result.reason_code == "MEMORY_TO_MEMORYSTORE"
    assert service.store.get_project("brain-eleven")["revision"] == 1


def test_missing_target_and_untrusted_provenance_never_write(tmp_path):
    service, _ = _setup(tmp_path)
    missing_target = StateBoundary(tmp_path).apply(_proposal("RESOLVE_BLOCKER"), expected_revision=1, source=SOURCE, commit=True)
    untrusted = StateBoundary(tmp_path).apply(_proposal(), expected_revision=1, source={"type": "ai_proposed", "reference": "guess"}, commit=True)

    assert missing_target.status == BoundaryStatus.REVIEW_REQUIRED.value
    assert missing_target.reason_code == "LIFECYCLE_TARGET_REQUIRED"
    assert untrusted.status == BoundaryStatus.REVIEW_REQUIRED.value
    assert untrusted.reason_code == "INVALID_PROVENANCE"
    assert service.store.get_project("brain-eleven")["revision"] == 1


def test_wrong_project_and_stale_revision_fail_closed(tmp_path):
    service, _ = _setup(tmp_path)
    wrong = StateBoundary(tmp_path).apply(_proposal(project_id="other-project"), expected_revision=1, source=SOURCE, commit=True)
    stale = StateBoundary(tmp_path).apply(_proposal(), expected_revision=0, source=SOURCE, commit=True)

    assert wrong.status == BoundaryStatus.SCOPE_ERROR.value
    assert wrong.reason_code == "PROJECT_UNKNOWN"
    assert stale.status == BoundaryStatus.STALE_INPUT.value
    assert service.store.get_project("brain-eleven")["revision"] == 1


def test_typed_requirement_and_phase_routes_are_supported(tmp_path):
    service, _ = _setup(tmp_path)
    boundary = StateBoundary(tmp_path)
    requirement = StateMutationProposal(
        candidate_id="cand_req_01", candidate_type="STATE_MUTATION", project_id="brain-eleven", commitment="OBSERVED",
        occurred_at=None, confidence=0.9, evidence_refs=("evd_02",), operation="ADD_REQUIREMENT", text="Security requirement must be met."
    )
    phase = StateMutationProposal(
        candidate_id="cand_phase_01", candidate_type="STATE_MUTATION", project_id="brain-eleven", commitment="OBSERVED",
        occurred_at=None, confidence=0.9, evidence_refs=("evd_03",), operation="SET_CURRENT_PHASE", text="Current Phase 17 is active."
    )
    results = boundary.apply_batch((requirement, phase), project_id="brain-eleven", source=SOURCE, commit=True, now="2026-09-05T10:02:00Z")

    assert [item.status for item in results] == ["SUCCESS", "SUCCESS"]
    state = service.store.get_project("brain-eleven")
    assert state["revision"] == 3
    assert state["requirements"][0]["status"] == "ACTIVE"
    assert state["current"]["milestone"]["phase_id"] == "phase-17"
