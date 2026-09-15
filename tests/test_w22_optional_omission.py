"""W-22 tests for the V2 optional-omission budget contract."""

from __future__ import annotations

import json
from types import SimpleNamespace

from context_compiler_v2 import BudgetContract, CompilationRequest, ContextCompilerV2
from context_compiler_v2.models import TokenEstimate, UtilityProfile
from context_compiler_v2.planner import choose
from context_compiler_v2.utility import CandidateDraft

from .test_context_compiler_v2 import _configured, _resolved
from .test_context_compiler_v2_hardening import _write_config


def _draft(candidate_id: str, cost: int = 10) -> CandidateDraft:
    resolution = SimpleNamespace(
        candidate_id=candidate_id,
        status="AUTHORITATIVE",
        source_type="memory",
        project_id="project-a",
        canonical_ref={"authority": "memory", "memory_id": candidate_id},
        claim=SimpleNamespace(dedup_fingerprint=None),
    )
    evidence = SimpleNamespace(resolution=resolution, project_id="project-a", text="safe")
    estimate = TokenEstimate(cost, "CONSERVATIVE_ESTIMATE", "test", "1", cost)
    utility = UtilityProfile(
        candidate_id=candidate_id,
        role="DECISION",
        tier=3,
        mandatory=False,
        task_fit="related",
        epistemic_status="AUTHORITATIVE",
        specificity="project_specific",
        redundancy_group=None,
        estimated_cost=estimate,
    )
    return CandidateDraft(evidence, "DECISION", 3, False, "related", None, "safe", utility)


def test_planner_marks_optional_omission_disallowed_without_omission_ledger():
    budget = BudgetContract(64, minimum_headroom_tokens=0, allow_optional_omission=False)

    plan = choose([_draft("optional-1", cost=10)], budget, allow_history=False, base_cost=60)

    assert plan.optional_omission_disallowed is True
    assert plan.optional_omission_reason == "budget_exhausted"
    assert plan.selected == ()
    assert plan.omitted == ()


def test_false_flag_fails_profile_budget_before_writing_context(tmp_path):
    context, state, _project = _configured(tmp_path)
    resolution = _resolved(tmp_path, context)
    memory_before = (tmp_path / ".claude" / "validated-memory.json").read_bytes()
    state_before = (tmp_path / ".claude" / "project-state.json").read_bytes()
    _write_config(tmp_path, optional_percent=0, max_optional_items=32)

    request = CompilationRequest(
        context,
        resolution,
        BudgetContract(1024, minimum_headroom_tokens=32, allow_optional_omission=False),
    )
    result = ContextCompilerV2(tmp_path).compile(request)

    assert result.status == "INSUFFICIENT_BUDGET"
    assert result.error == "OPTIONAL_OMISSION_DISALLOWED"
    assert result.selected == ()
    assert result.rendered_context == ""
    assert result.telemetry["optional_omission_reason"] == "profile_budget_exhausted"
    assert (tmp_path / ".claude" / "validated-memory.json").read_bytes() == memory_before
    assert (tmp_path / ".claude" / "project-state.json").read_bytes() == state_before
    assert "atomic persistence" not in json.dumps(result.manifest_dict()).casefold()


def test_false_flag_fails_profile_item_limit(tmp_path):
    context, _state, _project = _configured(tmp_path)
    resolution = _resolved(tmp_path, context)
    _write_config(tmp_path, optional_percent=100, max_optional_items=0)

    result = ContextCompilerV2(tmp_path).compile(
        CompilationRequest(
            context,
            resolution,
            BudgetContract(1024, minimum_headroom_tokens=32, allow_optional_omission=False),
        )
    )

    assert result.status == "INSUFFICIENT_BUDGET"
    assert result.error == "OPTIONAL_OMISSION_DISALLOWED"
    assert result.telemetry["optional_omission_reason"] == "profile_item_limit"


def test_false_flag_fails_final_render_overflow_before_removal(tmp_path):
    context, _state, _project = _configured(tmp_path)
    resolution = _resolved(tmp_path, context)

    class FinalOverflowEstimator:
        def estimate(self, text):
            is_fragment = text.startswith("- [")
            count = 1 if is_fragment or "- [" not in text else 999
            return TokenEstimate(count, "CONSERVATIVE_ESTIMATE", "test", "1", count)

    result = ContextCompilerV2(tmp_path, estimator=FinalOverflowEstimator()).compile(
        CompilationRequest(
            context,
            resolution,
            BudgetContract(100, minimum_headroom_tokens=32, allow_optional_omission=False),
        )
    )

    assert result.status == "INSUFFICIENT_BUDGET"
    assert result.error == "OPTIONAL_OMISSION_DISALLOWED"
    assert result.rendered_context == ""
    assert result.telemetry["optional_candidates"] > 0


def test_false_flag_all_fit_matches_default_context(tmp_path):
    context, _state, _project = _configured(tmp_path)
    resolution = _resolved(tmp_path, context)
    default = ContextCompilerV2(tmp_path).compile(
        CompilationRequest(context, resolution, BudgetContract(4096, minimum_headroom_tokens=32))
    )
    strict = ContextCompilerV2(tmp_path).compile(
        CompilationRequest(
            context,
            resolution,
            BudgetContract(4096, minimum_headroom_tokens=32, allow_optional_omission=False),
        )
    )

    assert strict.status == default.status
    assert strict.rendered_context == default.rendered_context
    assert [item.candidate_id for item in strict.selected] == [item.candidate_id for item in default.selected]


def test_true_flag_preserves_existing_profile_omission_behavior(tmp_path):
    context, state, project = _configured(tmp_path)
    state.add_constraint(
        "project-a", text="Durable data must never be lost.", expected_revision=2,
        source={"type": "user", "reference": "w22"},
        record_id="con_01J00000000000000000000000", now="2026-09-03T12:00:00Z",
    )
    from task_state_context import TaskStateComposer

    context = TaskStateComposer(tmp_path, project).compose("Implement atomic SQLite persistence.")
    resolution = _resolved(tmp_path, context)
    _write_config(tmp_path, optional_percent=0, max_optional_items=0)

    result = ContextCompilerV2(tmp_path).compile(
        CompilationRequest(context, resolution, BudgetContract(1024, minimum_headroom_tokens=32))
    )

    assert result.status in {"SUCCESS", "DEGRADED"}
    assert any(item.reason == "profile_budget_exhausted" for item in result.omitted)
