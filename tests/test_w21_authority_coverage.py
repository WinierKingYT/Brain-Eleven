"""W-21 tests for fail-closed V2 authority coverage."""

from pathlib import Path
from types import SimpleNamespace

from retrieval_decision_v2 import DecisionOptions, RetrievalDecisionEngine


def _candidate(candidate_id, *, project_id="brain-eleven", lifecycle="ACTIVE", source_revision=7):
    return SimpleNamespace(
        candidate_id=candidate_id,
        source_type="memory",
        project_id=project_id,
        content_type="decision",
        lifecycle=lifecycle,
        source_revision=source_revision,
        canonical_ref={"authority": "memory", "memory_id": candidate_id},
        retrieved_by=("lexical",),
        match_signals=("decision",),
        retrieval_score=0.8,
    )


def _authority(candidate, *, project_id=None, status="AUTHORITATIVE"):
    return SimpleNamespace(
        candidate_id=candidate.candidate_id,
        project_id=candidate.project_id if project_id is None else project_id,
        status=status,
        claim=SimpleNamespace(dedup_fingerprint=None),
    )


def _inputs(candidates, authority=None, *, router_status="SUCCESS", authority_status="SUCCESS", scope_mode="CURRENT_PROJECT"):
    task = SimpleNamespace(
        task=SimpleNamespace(
            project=SimpleNamespace(project_id="brain-eleven"),
            intent=SimpleNamespace(value="IMPLEMENT"),
            context_needs=("project_decisions",),
            explicit_constraints=(),
            inherited_constraints=(),
        ),
        state=SimpleNamespace(active_blockers=()),
    )
    scope = SimpleNamespace(mode=scope_mode, project_ids=("brain-eleven",), include_global=True)
    router = SimpleNamespace(
        status=router_status,
        plan=SimpleNamespace(scope=scope),
        input_revisions={"memory": 7, "state": {}},
        candidates=tuple(candidates),
    )
    resolution = None
    if authority is not None:
        resolution = SimpleNamespace(
            status=authority_status,
            input_revisions={"memory": 7, "state": {}},
            candidates=tuple(authority),
        )
    return task, router, resolution


def test_missing_authority_fails_closed_without_content():
    candidate = _candidate("mem-private")
    task, router, _ = _inputs([candidate])

    result = RetrievalDecisionEngine().select(task, router, None)

    assert result.status == "FAILED"
    assert result.error == "AUTHORITY_COVERAGE_UNAVAILABLE"
    assert result.selected == ()
    assert result.telemetry["authority_coverage"] == "missing"
    assert "mem-private" not in repr(result.to_dict())


def test_empty_authority_fails_closed_for_eligible_candidate():
    candidate = _candidate("mem-empty")
    task, router, resolution = _inputs([candidate], [], authority_status="EMPTY")

    result = RetrievalDecisionEngine().select(task, router, resolution)

    assert result.status == "FAILED"
    assert result.error == "AUTHORITY_COVERAGE_UNAVAILABLE"
    assert result.telemetry["authority_coverage"] == "empty"


def test_partial_authority_coverage_fails_closed():
    first = _candidate("mem-one")
    second = _candidate("mem-two")
    task, router, resolution = _inputs([first, second], [_authority(first)])

    result = RetrievalDecisionEngine().select(task, router, resolution)

    assert result.status == "FAILED"
    assert result.selected == ()
    assert result.telemetry["authority_coverage"] == "partial"
    assert result.telemetry["eligible_candidates"] == 2


def test_duplicate_authority_rows_fail_before_mapping_collapse():
    candidate = _candidate("mem-duplicate")
    task, router, resolution = _inputs([candidate], [_authority(candidate), _authority(candidate)])

    result = RetrievalDecisionEngine().select(task, router, resolution)

    assert result.status == "FAILED"
    assert result.error == "AUTHORITY_COVERAGE_UNAVAILABLE"
    assert result.telemetry["authority_coverage"] == "duplicate"


def test_duplicate_authority_id_in_foreign_project_is_not_selected():
    candidate = _candidate("mem-foreign")
    task, router, resolution = _inputs(
        [candidate],
        [_authority(candidate), _authority(candidate, project_id="other-project")],
    )

    result = RetrievalDecisionEngine().select(task, router, resolution)

    assert result.status == "FAILED"
    assert result.selected == ()
    assert result.telemetry["authority_coverage"] == "duplicate"


def test_complete_success_coverage_preserves_selection_and_truthful_telemetry():
    candidate = _candidate("mem-complete")
    task, router, resolution = _inputs([candidate], [_authority(candidate)])

    result = RetrievalDecisionEngine().select(task, router, resolution)

    assert result.status == "SUCCESS"
    assert [item.candidate_id for item in result.selected] == ["mem-complete"]
    assert result.telemetry["authority_used"] is True
    assert result.telemetry["authority_coverage"] == "full"


def test_complete_degraded_coverage_keeps_degraded_visibility():
    candidate = _candidate("mem-degraded")
    task, router, resolution = _inputs([candidate], [_authority(candidate)], authority_status="DEGRADED")

    result = RetrievalDecisionEngine().select(task, router, resolution)

    assert result.status == "DEGRADED"
    assert result.degraded_reasons == ("AUTHORITY_DEGRADED",)
    assert result.telemetry["authority_used"] is True


def test_no_eligible_candidates_are_empty_without_authority_requirement():
    candidate = _candidate("mem-other", project_id="other-project")
    task, router, _ = _inputs([candidate])

    result = RetrievalDecisionEngine().select(task, router, None)

    assert result.status == "EMPTY"
    assert result.selected == ()
    assert result.omitted["mem-other"] == "SCOPE_FILTERED"
    assert result.telemetry["authority_used"] is False
    assert result.telemetry["authority_coverage"] == "empty"


def test_off_mode_does_not_require_authority():
    candidate = _candidate("mem-off")
    task, router, _ = _inputs([candidate])

    result = RetrievalDecisionEngine().select(task, router, None, options=DecisionOptions(mode="OFF"))

    assert result.status == "EMPTY"
    assert result.selected == ()
    assert result.telemetry == {"mode": "OFF", "selected": 0}


def test_existing_authority_scope_mismatch_omits_only_foreign_row():
    allowed = _candidate("mem-allowed")
    foreign = _candidate("mem-foreign-authority")
    task, router, resolution = _inputs(
        [allowed, foreign],
        [_authority(allowed), _authority(foreign, project_id="other-project")],
    )

    result = RetrievalDecisionEngine().select(task, router, resolution)

    assert result.status == "SUCCESS"
    assert [item.candidate_id for item in result.selected] == ["mem-allowed"]
    assert result.omitted["mem-foreign-authority"] == "AUTHORITY_SCOPE_MISMATCH"


def test_selection_does_not_mutate_external_files(tmp_path: Path):
    marker = tmp_path / "sentinel.json"
    marker.write_text('{"revision": 3}', encoding="utf-8")
    before = marker.read_bytes()
    candidate = _candidate("mem-read-only")
    task, router, resolution = _inputs([candidate], [_authority(candidate)])

    RetrievalDecisionEngine().select(task, router, resolution)

    assert marker.read_bytes() == before
