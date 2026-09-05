"""PRE-09 diversity, coverage, and context-density contract tests."""

from types import SimpleNamespace

import pytest

from context_density_v2 import ContextDensityEngine, DensityOptions
from context_density_v2.models import DensityContractError


def _candidate(candidate_id, *, needs=("need_decisions",), score=0.8, group=None, tokens=10, project_id="brain-eleven"):
    return SimpleNamespace(
        candidate_id=candidate_id,
        source_type="memory",
        project_id=project_id,
        content_type="decision",
        lifecycle="ACTIVE",
        canonical_ref={"authority": "memory", "memory_id": candidate_id, "dedup_fingerprint": group or candidate_id, "estimated_tokens": tokens},
        needs=needs,
        decision_score=score,
        retrieval_score=score,
    )


def _result(candidates, needs=(SimpleNamespace(need_id="need_decisions", priority="high"),)):
    return SimpleNamespace(status="SUCCESS", input_revisions={"memory": 7, "state": {}}, selected=tuple(candidates), need_plan=SimpleNamespace(needs=needs))


def test_diversity_omits_near_duplicates_and_stays_content_free():
    result = ContextDensityEngine().select(_result([
        _candidate("mem-a", score=0.9, group="db"),
        _candidate("mem-b", score=0.8, group="db"),
        _candidate("mem-c", score=0.7, group="cache"),
    ]))

    assert result.status == "DEGRADED"
    assert [item.candidate_id for item in result.selected] == ["mem-a", "mem-c"]
    assert result.omitted["mem-b"] == "REDUNDANT_CONTEXT"
    assert all("content" not in item.to_dict() for item in result.selected)
    assert result.metrics["redundancy_rate"] == 0.0


def test_critical_needs_are_preserved_before_optional_density_selection():
    needs = (
        SimpleNamespace(need_id="need_state", priority="critical"),
        SimpleNamespace(need_id="need_lessons", priority="normal"),
    )
    result = ContextDensityEngine().select(_result([
        _candidate("state-1", needs=("need_state",), score=0.2),
        _candidate("lesson-1", needs=("need_lessons",), score=0.99),
    ], needs), options=DensityOptions(max_selected=0))

    assert result.status == "FAILED"
    assert result.error == "MANDATORY_CONTEXT_UNSATISFIED"


def test_critical_need_recall_and_density_metrics_are_deterministic():
    needs = (
        SimpleNamespace(need_id="need_state", priority="critical"),
        SimpleNamespace(need_id="need_lessons", priority="normal"),
    )
    selected = [_candidate("state-1", needs=("need_state",), tokens=20), _candidate("noise-1", needs=(), tokens=10)]
    first = ContextDensityEngine().select(_result(selected, needs))
    second = ContextDensityEngine().select(_result(selected, needs))

    assert first.to_dict() == second.to_dict()
    assert first.metrics["critical_need_recall"] == 1.0
    assert first.metrics["useful_context_density"] == 0.666667
    assert first.metrics["context_waste_ratio"] == 0.333333
    assert first.need_coverage["need_state"] == ("state-1",)
    assert first.need_coverage["need_lessons"] == ()


def test_same_group_can_cover_a_missing_critical_need():
    needs = (
        SimpleNamespace(need_id="need_state", priority="critical"),
        SimpleNamespace(need_id="need_constraints", priority="critical"),
    )
    result = ContextDensityEngine().select(_result([
        _candidate("state-1", needs=("need_state",), group="same"),
        _candidate("constraint-1", needs=("need_constraints",), group="same"),
    ], needs))

    assert {item.candidate_id for item in result.selected} == {"state-1", "constraint-1"}
    assert result.metrics["critical_need_recall"] == 1.0


def test_off_and_upstream_failure_are_fail_closed():
    result = _result([_candidate("mem-1")])
    assert ContextDensityEngine().select(result, options=DensityOptions(mode="OFF")).status == "EMPTY"
    stale = SimpleNamespace(status="STALE_INPUT", input_revisions={"memory": 8})
    assert ContextDensityEngine().select(stale).status == "STALE_INPUT"
    failed = SimpleNamespace(status="FAILED", input_revisions={"memory": 8})
    assert ContextDensityEngine().select(failed).status == "FAILED"


def test_contract_rejects_unbounded_or_invalid_options():
    with pytest.raises(DensityContractError):
        DensityOptions(mode="ACTIVE")
    with pytest.raises(DensityContractError):
        DensityOptions(max_selected=-1)
    with pytest.raises(DensityContractError):
        DensityOptions(diversity_lambda=1.1)
