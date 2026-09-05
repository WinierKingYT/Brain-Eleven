"""PRE-10 production-hardening tests for Compiler V2."""

from __future__ import annotations

import json

import pytest

from context_compiler_v2 import BudgetContract, CompilationRequest, ContextCompilerV2
from context_compiler_v2.cache import CompilerCache
from context_compiler_v2.models import TokenEstimate
from context_compiler_v2.profile_policy import DEFAULT_PROFILE_BUDGETS
from context_compiler_v2.safety import contains_secret
from task_state_context import TaskStateComposer

from .test_context_compiler_v2 import _configured, _resolved


def _write_config(vault, *, optional_percent: int, max_optional_items: int) -> None:
    profiles = {
        name: {
            "optional_budget_percent": optional_percent if name == "implementation" else policy.optional_budget_percent,
            "max_optional_items": max_optional_items if name == "implementation" else policy.max_optional_items,
            "mandatory_roles": list(policy.mandatory_roles),
        }
        for name, policy in DEFAULT_PROFILE_BUDGETS.items()
    }
    (vault / ".claude" / "context-compiler-v2.json").write_text(json.dumps({
        "schema_version": 1,
        "policy_version": "context-compiler-v2-policy-v1",
        "cache_enabled": True,
        "max_rebalance_iterations": 8,
        "default_mode": "SHADOW",
        "profile_budgets": profiles,
    }), encoding="utf-8")


def test_profile_budget_preserves_mandatory_and_bounds_optional_context(tmp_path):
    context, state, project = _configured(tmp_path)
    state.add_constraint(
        "project-a", text="Durable data must never be lost.", expected_revision=2,
        source={"type": "user", "reference": "pre10"},
        record_id="con_01J00000000000000000000000", now="2026-09-03T12:00:00Z",
    )
    context = TaskStateComposer(tmp_path, project).compose("Implement atomic SQLite persistence.")
    _write_config(tmp_path, optional_percent=0, max_optional_items=0)
    resolution = _resolved(tmp_path, context)

    result = ContextCompilerV2(tmp_path).compile(
        CompilationRequest(context, resolution, BudgetContract(1024, minimum_headroom_tokens=32))
    )

    assert result.status in {"SUCCESS", "DEGRADED"}
    assert {item.role for item in result.selected} >= {"CONSTRAINT"}
    assert result.telemetry["final_measurement_verified"] is True
    assert result.budget["profile_budget"]["optional_budget_percent"] == 0
    assert any(item.reason in {"profile_budget_exhausted", "profile_item_limit"} for item in result.omitted)


def test_malformed_profile_budget_policy_fails_closed(tmp_path):
    context, _state, _project = _configured(tmp_path)
    resolution = _resolved(tmp_path, context)
    policy = tmp_path / ".claude" / "context-compiler-v2.json"
    policy.write_text(json.dumps({
        "schema_version": 1,
        "policy_version": "context-compiler-v2-policy-v1",
        "cache_enabled": True,
        "max_rebalance_iterations": 8,
        "default_mode": "SHADOW",
        "profile_budgets": {"implementation": {}},
    }), encoding="utf-8")

    result = ContextCompilerV2(tmp_path).compile(
        CompilationRequest(context, resolution, BudgetContract(1024, minimum_headroom_tokens=32))
    )

    assert result.status == "FAILED"
    assert not result.selected


def test_final_measurement_nondeterminism_fails_closed(tmp_path):
    context, _state, _project = _configured(tmp_path)
    resolution = _resolved(tmp_path, context)

    class FlappingEstimator:
        def __init__(self):
            self.calls = 0

        def estimate(self, text):
            self.calls += 1
            return TokenEstimate(
                count=self.calls,
                mode="CONSERVATIVE_ESTIMATE",
                adapter="test",
                version="1",
                byte_count=len(text.encode("utf-8")),
            )

    result = ContextCompilerV2(tmp_path, estimator=FlappingEstimator()).compile(
        CompilationRequest(context, resolution, BudgetContract(2048, minimum_headroom_tokens=32))
    )

    assert result.status == "FAILED"
    assert "deterministic" in result.error.casefold()


def test_cache_rejects_all_model_facing_content_fields(tmp_path):
    cache = CompilerCache(tmp_path)
    with pytest.raises(ValueError):
        cache.store("key", {"memory": 1}, {"text": "private content"})
    with pytest.raises(ValueError):
        cache.store("key", {"memory": 1}, {"nested": {"rendered_text": "private content"}})


def test_secret_screening_covers_jwt_private_key_and_provider_tokens():
    assert contains_secret("eyJheader-value.example-payload.signature-value")
    assert contains_secret("-----BEGIN PRIVATE KEY-----")
    assert contains_secret("ghp_123456789012345678901234")
