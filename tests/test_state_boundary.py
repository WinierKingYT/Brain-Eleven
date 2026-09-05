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


def _proposal(operation="ADD_BLOCKER", *, project_id="brain-eleven", commitment="OBSERVED", text="Authentication tests are failing."):
    return StateMutationProposal(
        candidate_id="cand_state_01",
        candidate_type="STATE_MUTATION",
        project_id=project_id,
        commitment=commitment,
        occurred_at=None,
        confidence=0.94,
        evidence_refs=("evd_01",),
        operation=operation,
        text=text,
    )


def test_blocker_routes_to_state_without_memory_write(tmp_path):
    service, _ = _setup(tmp_path)
    before_memory = service.memory_store.load()
    result = StateBoundary(tmp_path).apply(_proposal(), expected_revision=1, source=SOURCE, commit=True, now="2026-09-05T10:01:00Z")

    assert result.status == BoundaryStatus.SUCCESS.value
    assert result.canonical_write is True
    assert service.store.get_project("brain-eleven")["blockers"][0]["text"] == "Authentication tests are failing."
    after_memory = service.memory_store.load()
    assert after_memory["revision"] == before_memory["revision"]
    assert after_memory["validated_memory"] == before_memory["validated_memory"]
    assert after_memory["rejected_memory"] == before_memory["rejected_memory"]


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


def test_classification_is_content_free_and_memory_open_loop_stays_on_memory_route(tmp_path):
    memory = NewMemoryCandidate(
        candidate_id="cand_loop_01", candidate_type="NEW_MEMORY", project_id="brain-eleven", commitment="COMMITTED",
        occurred_at=None, confidence=0.9, evidence_refs=("evd_04",), memory_type="open_loop", scope="project", content="Open question"
    )

    assert StateBoundary.classify(memory).reason_code == "OPEN_LOOP_TO_MEMORY"
    assert StateBoundary.classify(_proposal()).reason_code == "STATE_PROPOSAL_READY"
    assert StateBoundary.classify({}).reason_code == "INVALID_CANDIDATE"
    assert StateBoundary.classify({"candidate_id": "cand_x", "candidate_type": "OTHER"}).reason_code == "UNSUPPORTED_CANDIDATE_TYPE"


def test_dry_run_and_scope_or_provenance_errors_do_not_write(tmp_path):
    service, _ = _setup(tmp_path)
    boundary = StateBoundary(tmp_path)

    dry = boundary.apply(_proposal(), expected_revision=1)
    unresolved = boundary.apply(_proposal(project_id=None), expected_revision=1, commit=True, source=SOURCE)
    missing_source = boundary.apply(_proposal(), expected_revision=1, commit=True)
    bad_source = boundary.apply(_proposal(), expected_revision=1, commit=True, source={"type": "user", "reference": ""})

    assert dry.status == BoundaryStatus.DRY_RUN.value
    assert unresolved.reason_code == "PROJECT_UNRESOLVED"
    assert missing_source.reason_code == "INVALID_PROVENANCE"
    assert bad_source.reason_code == "INVALID_PROVENANCE"
    assert service.store.get_project("brain-eleven")["revision"] == 1


def test_all_supported_typed_operations_are_delegated(tmp_path):
    service, _ = _setup(tmp_path)
    boundary = StateBoundary(tmp_path)
    source = {"type": "tool", "reference": "capture-job-1"}

    work = boundary.apply(_proposal("ADD_WORK_ITEM", text="Implement the state boundary."), expected_revision=1, source=source, commit=True)
    objective = boundary.apply(_proposal("SET_OBJECTIVE", text="Protect state authority."), expected_revision=2, source=source, commit=True)
    requirement = boundary.apply(_proposal("ADD_REQUIREMENT", text="State must stay separate."), expected_revision=3, source=source, commit=True)
    phase = boundary.apply(_proposal("SET_CURRENT_PHASE", text="Phase 17 is active."), expected_revision=4, source=source, commit=True)

    assert [item.status for item in (work, objective, requirement, phase)] == ["SUCCESS"] * 4
    state = service.store.get_project("brain-eleven")
    assert state["revision"] == 5
    assert state["work_items"][0]["status"] == "TODO"
    assert state["current"]["objective"]["text"] == "Protect state authority."


def test_resolution_requires_target_but_succeeds_with_explicit_typed_target(tmp_path):
    service, _ = _setup(tmp_path)
    boundary = StateBoundary(tmp_path)
    source = {"type": "user", "reference": "correction"}
    blocker = boundary.apply(_proposal(), expected_revision=1, source=source, commit=True)
    blocker_id = service.store.get_project("brain-eleven")["blockers"][0]["id"]
    resolved = boundary.apply(_proposal("RESOLVE_BLOCKER", text="Deployment blocker resolved."), expected_revision=2, source=source, commit=True, target_id=blocker_id)

    assert resolved.status == BoundaryStatus.SUCCESS.value
    assert service.store.get_project("brain-eleven")["blockers"][0]["status"] == "RESOLVED"


def test_invalid_phase_text_and_unknown_operation_fail_without_revision_change(tmp_path):
    service, _ = _setup(tmp_path)
    boundary = StateBoundary(tmp_path)
    source = {"type": "system", "reference": "worker"}
    bad_phase = boundary.apply(_proposal("SET_CURRENT_PHASE", text="The current milestone is active."), expected_revision=1, source=source, commit=True)
    unknown = boundary.apply(_proposal("NOT_A_TYPED_OPERATION"), expected_revision=1, source=source, commit=True)
    empty = boundary.apply(_proposal(text=""), expected_revision=1, source=source, commit=True)

    assert bad_phase.reason_code == "PHASE_TARGET_REQUIRED"
    assert unknown.reason_code == "UNSUPPORTED_STATE_OPERATION"
    assert empty.reason_code == "TEXT_REQUIRED"
    assert service.store.get_project("brain-eleven")["revision"] == 1


def test_archived_project_is_read_only_and_batch_rejects_other_projects(tmp_path):
    service, project_root = _setup(tmp_path)
    ProjectRegistry(tmp_path).set_status("brain-eleven", "archived")
    archived = StateBoundary(tmp_path).apply(_proposal(), expected_revision=1, source=SOURCE, commit=True)
    assert archived.status == BoundaryStatus.SCOPE_ERROR.value
    assert archived.reason_code == "PROJECT_ARCHIVED"

    other = tmp_path / "other"
    ProjectRegistry(tmp_path).register(other, project_id="other-project")
    StateService(tmp_path).init_project("other-project", source=SOURCE)
    result = StateBoundary(tmp_path).apply_batch((_proposal(project_id="other-project"),), project_id="brain-eleven", source=SOURCE, commit=True)
    assert result[0].reason_code == "WRONG_PROJECT_PROPOSAL"
