"""Phase 16 deterministic public evaluation tests."""

from __future__ import annotations

from evals.task_state_eval import run_task_state_evaluation


def test_smoke_suite_has_twenty_task_and_state_cases_with_all_hard_gates_green():
    report = run_task_state_evaluation(suite="smoke")

    assert report["metrics"]["task_case_count"] == 20
    assert report["metrics"]["state_case_count"] == 20
    assert all(invariant["state"] == "pass" for invariant in report["invariants"].values())


def test_public_suite_is_deterministic_and_contains_dev_plus_test_boundaries():
    first = run_task_state_evaluation(suite="public")
    second = run_task_state_evaluation(suite="public")

    assert first == second
    assert first["metrics"]["task_case_count"] == 24
    assert first["metrics"]["state_case_count"] == 24
