"""PRE-08 retrieval decision contract tests."""

from types import SimpleNamespace

import pytest

from retrieval_decision_v2 import (
    DecisionOptions,
    DecisionResult,
    Need,
    NeedPlan,
    RetrievalDecisionEngine,
    SelectedCandidate,
)
from retrieval_decision_v2.models import RetrievalDecisionContractError


def _candidate(candidate_id, project_id="brain-eleven", content_type="decision", score=0.8, lifecycle="ACTIVE", source_type="memory", fingerprint=None, source_revision=7):
    return SimpleNamespace(
        candidate_id=candidate_id,
        source_type=source_type,
        project_id=project_id,
        content_type=content_type,
        lifecycle=lifecycle,
        source_revision=source_revision,
        canonical_ref={"authority": source_type, "memory_id": candidate_id},
        retrieved_by=("lexical",),
        match_signals=(content_type,),
        retrieval_score=score,
    )


def _inputs(candidates, *, project_id="brain-eleven", scope_mode="CURRENT_PROJECT", project_ids=("brain-eleven",), authority=None, status="SUCCESS"):
    task = SimpleNamespace(
        project=SimpleNamespace(project_id=project_id),
        intent=SimpleNamespace(value="IMPLEMENT"),
        context_needs=("project_decisions",),
        explicit_constraints=(),
        inherited_constraints=(),
    )
    state = SimpleNamespace(active_blockers=())
    scope = SimpleNamespace(mode=scope_mode, project_ids=project_ids, include_global=True)
    plan = SimpleNamespace(scope=scope)
    router = SimpleNamespace(status=status, plan=plan, input_revisions={"memory": 7, "state": {}}, candidates=tuple(candidates))
    resolution = None
    if authority is not None:
        resolution = SimpleNamespace(status="SUCCESS", input_revisions={"memory": 7, "state": {}}, candidates=tuple(authority))
    return SimpleNamespace(task=task, state=state), router, resolution


def _authority(candidate, status="AUTHORITATIVE", fingerprint=None):
    claim = SimpleNamespace(dedup_fingerprint=fingerprint)
    return SimpleNamespace(candidate_id=candidate.candidate_id, project_id=candidate.project_id, status=status, claim=claim)


def test_default_selection_is_project_scoped_and_content_free():
    current = _candidate("mem-current")
    other = _candidate("mem-other", project_id="other-project")
    global_memory = _candidate("mem-global", project_id=None)
    task, router, authority = _inputs([current, other, global_memory], authority=[_authority(current), _authority(global_memory)])

    result = RetrievalDecisionEngine().select(task, router, authority)

    assert result.status == "SUCCESS"
    assert [item.candidate_id for item in result.selected] == ["mem-current", "mem-global"]
    assert "mem-other" in result.omitted
    assert all("content" not in item.to_dict() for item in result.selected)


def test_hard_lifecycle_and_authority_filters_run_before_scoring():
    active = _candidate("mem-active", score=0.1)
    superseded = _candidate("mem-old", score=1.0, lifecycle="SUPERSEDED")
    resolved = _candidate("mem-resolved", score=1.0, lifecycle="RESOLVED")
    task, router, authority = _inputs([active, superseded, resolved], authority=[_authority(active), _authority(superseded, "SUPERSEDED"), _authority(resolved, "HISTORICAL")])

    result = RetrievalDecisionEngine().select(task, router, authority)

    assert [item.candidate_id for item in result.selected] == ["mem-active"]
    assert result.omitted["mem-old"] == "LIFECYCLE_FILTERED"
    assert result.omitted["mem-resolved"] == "LIFECYCLE_FILTERED"


def test_resolution_mismatch_is_stale_and_never_selects():
    candidate = _candidate("mem-1")
    task, router, _ = _inputs([candidate])
    resolution = SimpleNamespace(status="SUCCESS", input_revisions={"memory": 8, "state": {}}, candidates=(_authority(candidate),))

    result = RetrievalDecisionEngine().select(task, router, resolution)

    assert result.status == "STALE_INPUT"
    assert result.selected == ()


def test_selected_projects_never_compare_or_leak_other_projects():
    allowed = _candidate("mem-a", project_id="project-a")
    forbidden = _candidate("mem-b", project_id="project-b", score=1.0)
    task, router, authority = _inputs([allowed, forbidden], project_id="project-a", scope_mode="SELECTED_PROJECTS", project_ids=("project-a",), authority=[_authority(allowed), _authority(forbidden)])

    result = RetrievalDecisionEngine().select(task, router, authority)

    assert [item.candidate_id for item in result.selected] == ["mem-a"]
    assert result.omitted["mem-b"] == "SCOPE_FILTERED"


def test_duplicate_fingerprint_is_reduced_deterministically_and_budget_is_explicit():
    first = _candidate("mem-a", score=0.7, fingerprint="fp")
    second = _candidate("mem-b", score=0.9, fingerprint="fp")
    third = _candidate("mem-c", score=0.2)
    task, router, authority = _inputs([first, second, third], authority=[_authority(first, fingerprint="fp"), _authority(second, fingerprint="fp"), _authority(third)])

    result = RetrievalDecisionEngine().select(task, router, authority, options=DecisionOptions(max_selected=1))

    assert [item.candidate_id for item in result.selected] == ["mem-b"]
    assert result.omitted["mem-a"] == "REDUNDANT_CLAIM"
    assert result.omitted["mem-c"] == "DECISION_BUDGET"


def test_off_mode_and_router_scope_errors_are_fail_closed():
    candidate = _candidate("mem-1")
    task, router, authority = _inputs([candidate], authority=[_authority(candidate)])
    assert RetrievalDecisionEngine().select(task, router, authority, options=DecisionOptions(mode="OFF")).status == "EMPTY"

    bad_task, bad_router, _ = _inputs([candidate], authority=None, project_ids=("different-project",))
    assert RetrievalDecisionEngine().select(bad_task, bad_router).status == "SCOPE_ERROR"


def test_contracts_reject_invalid_values_and_normalize_content_free_output():
    with pytest.raises(RetrievalDecisionContractError):
        DecisionOptions(mode="ACTIVE")
    with pytest.raises(RetrievalDecisionContractError):
        DecisionOptions(max_selected=-1)
    with pytest.raises(RetrievalDecisionContractError):
        Need("", "decision")
    with pytest.raises(RetrievalDecisionContractError):
        NeedPlan((Need("same", "decision"), Need("same", "lesson")))
    with pytest.raises(RetrievalDecisionContractError):
        SelectedCandidate("m", "memory", None, "decision", "ACTIVE", {}, (), (), 0.1, 0.1)
    result = DecisionResult("EMPTY", "policy", {"memory": 1}, NeedPlan())
    assert "content" not in result.to_dict()
    assert result.to_dict()["schema_version"] == 1


def test_error_inputs_and_scope_validation_fail_closed():
    engine = RetrievalDecisionEngine()
    task, router, authority = _inputs([])
    assert engine.select(task, SimpleNamespace(status="INVALID_TASK")).status == "FAILED"
    assert engine.select(task, SimpleNamespace(status="SCOPE_ERROR")).status == "SCOPE_ERROR"
    assert engine.select(task, SimpleNamespace(status="STALE_INPUT", input_revisions={"memory": 1})).status == "STALE_INPUT"
    assert engine.select(task, SimpleNamespace(status="SUCCESS")).status == "FAILED"
    bad_scope = SimpleNamespace(status="SUCCESS", plan=SimpleNamespace(scope=SimpleNamespace(mode="ALL", project_ids=(), include_global=True)), candidates=())
    assert engine.select(task, bad_scope).status == "SCOPE_ERROR"
    mismatch = SimpleNamespace(status="SUCCESS", plan=SimpleNamespace(scope=SimpleNamespace(mode="CURRENT_PROJECT", project_ids=("other",), include_global=True)), candidates=())
    assert engine.select(task, mismatch).status == "SCOPE_ERROR"
    empty_selected = SimpleNamespace(status="SUCCESS", plan=SimpleNamespace(scope=SimpleNamespace(mode="SELECTED_PROJECTS", project_ids=(), include_global=True)), candidates=())
    assert engine.select(task, empty_selected).status == "SCOPE_ERROR"
    failed_authority = SimpleNamespace(status="FAILED", input_revisions={"memory": 7}, candidates=())
    assert engine.select(task, router, failed_authority).status == "FAILED"
    stale_authority = SimpleNamespace(status="STALE_INPUT", input_revisions={"memory": 7}, candidates=())
    assert engine.select(task, router, stale_authority).status == "STALE_INPUT"
    mismatched_authority = SimpleNamespace(status="SUCCESS", input_revisions={"memory": 8}, candidates=())
    assert engine.select(task, router, mismatched_authority).status == "STALE_INPUT"


def test_history_state_matching_and_unresolved_authority_are_safe():
    resolved = _candidate("mem-resolved", lifecycle="RESOLVED", content_type="lesson")
    state = _candidate("state-1", content_type="blocker", source_type="state", project_id="brain-eleven")
    task, router, authority = _inputs([resolved, state], authority=[_authority(resolved, "UNRESOLVED"), _authority(state)])
    result = RetrievalDecisionEngine().select(task, router, authority, options=DecisionOptions(allow_history=True))
    assert {item.candidate_id for item in result.selected} == {"mem-resolved", "state-1"}
    assert result.status == "SUCCESS"
    by_id = {item.candidate_id: item for item in result.selected}
    assert by_id["mem-resolved"].reason_codes == ("AUTHORITY_UNRESOLVED",)


def test_duplicate_candidates_scope_mismatch_and_stale_source_are_omitted():
    first = _candidate("mem-1")
    duplicate = _candidate("mem-1", score=1.0)
    mismatch = _candidate("mem-2")
    stale_state = _candidate("state-1", source_type="state", source_revision=99)
    task, router, authority = _inputs([first, duplicate, mismatch, stale_state], authority=[_authority(first), _authority(mismatch, "AUTHORITATIVE", None), _authority(stale_state)])
    router.input_revisions["state"] = {"brain-eleven": 7}
    authority.input_revisions["state"] = {"brain-eleven": 7}
    authority.candidates[1].project_id = "other-project"
    result = RetrievalDecisionEngine().select(task, router, authority)
    assert result.selected[0].candidate_id == "mem-1"
    assert result.omitted["mem-1"] == "DUPLICATE_CANDIDATE"
    assert result.omitted["state-1"] == "STALE_CANDIDATE"
    assert result.omitted["mem-2"] == "AUTHORITY_SCOPE_MISMATCH"
    assert result.status == "DEGRADED"
