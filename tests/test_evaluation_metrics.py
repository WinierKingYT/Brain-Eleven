"""Deterministic metric and hard-leakage tests for Phase 15."""

from __future__ import annotations

from pathlib import Path

import pytest

from evals.baseline import BASELINE_CAPABILITIES, BASELINE_PROVIDER_ID
from evals.contracts import NormalizedEvaluationResult, SelectedContextItem
from evals.metrics import EvaluationMetricError, evaluate_selection
from evals.schema import load_fixture, load_tasks


ROOT = Path(__file__).resolve().parents[1]
FIXTURE_PATH = ROOT / "evals" / "fixtures" / "phase15-contract.json"
TASK_PATH = ROOT / "evals" / "corpus" / "dev" / "eleven-capture-atomic-save-001.json"


@pytest.fixture
def fixture():
    return load_fixture(FIXTURE_PATH)


@pytest.fixture
def task(fixture):
    return load_tasks([TASK_PATH], fixture)[0]


def _item(fixture, memory_id, *, project_id=None):
    memory = fixture.memories[memory_id]
    return SelectedContextItem(
        id=memory.memory_id,
        source_type="memory",
        project_id=memory.project_id if project_id is None else project_id,
        memory_type=memory.memory_type,
        status=memory.status,
        content=memory.content,
        score=0.9,
    )


def _result(task, items, *, capabilities=BASELINE_CAPABILITIES):
    return NormalizedEvaluationResult(
        task_id=task.task_id,
        provider_id=BASELINE_PROVIDER_ID,
        selected_items=tuple(items),
        source_memory_revision=0,
        project_id=task.project_id,
        retrieval_scope="default",
        capabilities=capabilities,
    )


def test_perfect_selection_has_full_precision_recall_and_no_violations(fixture, task):
    result = _result(
        task,
        [
            _item(fixture, "mem_markdown_source_of_truth"),
            _item(fixture, "mem_markdown_before_sqlite"),
            _item(fixture, "mem_windows_target"),
        ],
    )

    evaluation = evaluate_selection(task, fixture, result)

    assert evaluation.metrics.context_precision == 1.0
    assert evaluation.metrics.context_recall == 1.0
    assert evaluation.metrics.required_selected_count == 2
    assert evaluation.metrics.useful_selected_count == 1
    assert evaluation.violations == ()
    assert evaluation.passed is True


def test_missing_required_context_lowers_recall_without_inventing_a_safety_failure(fixture, task):
    result = _result(task, [_item(fixture, "mem_markdown_source_of_truth")])

    evaluation = evaluate_selection(task, fixture, result)

    assert evaluation.metrics.context_precision == 1.0
    assert evaluation.metrics.context_recall == 0.5
    assert evaluation.violations == ()


def test_wrong_project_and_forbidden_context_are_hard_failures(fixture, task):
    result = _result(task, [_item(fixture, "mem_promtgen_storage")])

    evaluation = evaluate_selection(task, fixture, result)

    assert evaluation.metrics.context_precision == 0.0
    assert evaluation.metrics.context_recall == 0.0
    assert evaluation.metrics.wrong_project_leakage_count == 1
    assert evaluation.metrics.forbidden_context_count == 1
    assert evaluation.invariants["wrong_project_leakage"] == "fail"
    assert evaluation.invariants["forbidden_context"] == "fail"
    assert evaluation.passed is False


def test_wrong_project_cannot_be_hidden_by_provider_metadata(fixture, task):
    result = _result(
        task,
        [_item(fixture, "mem_promtgen_storage", project_id=task.project_id)],
    )

    evaluation = evaluate_selection(task, fixture, result)

    assert evaluation.metrics.wrong_project_selected_count == 1
    assert evaluation.metrics.wrong_project_leakage_count == 1
    assert evaluation.invariants["wrong_project_leakage"] == "fail"


def test_superseded_selection_is_a_lifecycle_hard_failure(fixture, task):
    result = _result(task, [_item(fixture, "mem_superseded_save_rule")])

    evaluation = evaluate_selection(task, fixture, result)

    assert evaluation.metrics.superseded_selected_count == 1
    assert evaluation.metrics.superseded_leakage_count == 1
    assert evaluation.invariants["superseded_lifecycle_leakage"] == "fail"


def test_unlabeled_context_lowers_precision_without_becoming_a_safety_violation(fixture, task):
    unknown = SelectedContextItem(
        id="unknown_memory",
        source_type="memory",
        project_id=task.project_id,
        memory_type="decision",
        status="active",
        content="Unknown fixture record.",
        score=0.8,
    )

    evaluation = evaluate_selection(task, fixture, _result(task, [unknown]))

    assert evaluation.metrics.unlabeled_selection_count == 1
    assert evaluation.metrics.context_precision == 0.0
    assert evaluation.violations == ()


def test_unsupported_scope_capability_is_explicitly_not_a_pass(fixture, task):
    capabilities = dict(BASELINE_CAPABILITIES)
    capabilities["scope_isolation"] = "unsupported"
    result = _result(
        task,
        [_item(fixture, "mem_promtgen_storage")],
        capabilities=capabilities,
    )

    evaluation = evaluate_selection(task, fixture, result)

    assert evaluation.metrics.wrong_project_selected_count == 1
    assert evaluation.invariants["wrong_project_leakage"] == "unsupported"
    assert "wrong_project_leakage" not in evaluation.violations
    assert evaluation.invariants["forbidden_context"] == "fail"


def test_result_for_another_task_is_rejected(fixture, task):
    result = _result(task, [])
    wrong_task_result = NormalizedEvaluationResult(
        task_id="another_task",
        provider_id=result.provider_id,
        selected_items=result.selected_items,
        source_memory_revision=result.source_memory_revision,
        project_id=result.project_id,
        retrieval_scope=result.retrieval_scope,
        capabilities=result.capabilities,
    )

    with pytest.raises(EvaluationMetricError, match="does not match"):
        evaluate_selection(task, fixture, wrong_task_result)
