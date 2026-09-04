"""Phase 17 route-evaluation contract tests."""

from __future__ import annotations

import json

import pytest

from evals.router_evaluation import run_router_evaluation
from evals.router_expectations import RouterExpectationError, load_router_expectations
from evals.router_benchmark import run_router_benchmark
from evals.router_shadow import run_shadow_comparison


def test_router_expectation_suite_is_green_and_deterministic():
    first = run_router_evaluation()
    second = run_router_evaluation()

    assert first == second
    assert first["case_count"] == 7
    assert all(invariant["state"] == "pass" for invariant in first["invariants"].values())


def test_router_expectation_sidecar_rejects_unknown_schema_fields(tmp_path):
    sidecar = tmp_path / "invalid-router-expectations.json"
    sidecar.write_text(
        json.dumps({"schema_version": 1, "cases": [], "unsafe": True}),
        encoding="utf-8",
    )

    with pytest.raises(RouterExpectationError, match="invalid envelope"):
        load_router_expectations(sidecar)


def test_shadow_comparison_is_content_free_and_keeps_safety_gates_green():
    report = run_shadow_comparison()

    assert report["rollout_mode"] == "SHADOW"
    assert report["context_injection"] is False
    assert report["comparison"]["candidate_gate"]["passed"] is True
    assert "content" not in json.dumps(report).casefold()


def test_router_benchmark_reports_p50_and_p95_without_a_latency_gate():
    report = run_router_benchmark(sizes=(4,), samples=2)

    assert report["hard_latency_gate"] is False
    assert report["results"][0]["p50_ms"] >= 0
    assert report["results"][0]["p95_ms"] >= report["results"][0]["p50_ms"]
