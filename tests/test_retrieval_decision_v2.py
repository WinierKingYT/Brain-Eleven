"""PRE-08 retrieval decision contract tests."""

from types import SimpleNamespace

from retrieval_decision_v2 import DecisionOptions, RetrievalDecisionEngine


def _candidate(candidate_id, project_id="brain-eleven", content_type="decision", score=0.8, lifecycle="ACTIVE", source_type="memory", fingerprint=None):
    return SimpleNamespace(
        candidate_id=candidate_id,
        source_type=source_type,
        project_id=project_id,
        content_type=content_type,
        lifecycle=lifecycle,
        source_revision=7,
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
