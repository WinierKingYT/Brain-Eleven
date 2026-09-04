"""Reports must be deterministic and safety regressions must be visible."""

from __future__ import annotations

from pathlib import Path

import pytest

from evals.baseline import BASELINE_CAPABILITIES, BASELINE_PROVIDER_ID
from evals.contracts import NormalizedEvaluationResult, SelectedContextItem
from evals.reporting import (
    EvaluationReportError,
    build_evaluation_report,
    compare_evaluation_reports,
    read_evaluation_report,
    write_evaluation_report,
)
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


def _item(fixture, memory_id):
    memory = fixture.memories[memory_id]
    return SelectedContextItem(
        id=memory.memory_id,
        source_type="memory",
        project_id=memory.project_id,
        memory_type=memory.memory_type,
        status=memory.status,
        content=memory.content,
        score=0.9,
    )


def _result(task, items):
    return NormalizedEvaluationResult(
        task_id=task.task_id,
        provider_id=BASELINE_PROVIDER_ID,
        selected_items=tuple(items),
        source_memory_revision=0,
        project_id=task.project_id,
        retrieval_scope="default",
        capabilities=BASELINE_CAPABILITIES,
    )


def _perfect_result(fixture, task):
    return _result(
        task,
        [
            _item(fixture, "mem_markdown_source_of_truth"),
            _item(fixture, "mem_markdown_before_sqlite"),
            _item(fixture, "mem_windows_target"),
        ],
    )


def test_report_contains_deterministic_metrics_and_case_diagnostics(fixture, task, tmp_path):
    report = build_evaluation_report(
        fixture,
        [task],
        [_perfect_result(fixture, task)],
        suite="dev",
        source={"git_sha": "example", "corpus_version": 1},
    )
    output = tmp_path / "report.json"

    write_evaluation_report(output, report)
    loaded = read_evaluation_report(output)

    assert loaded == report
    assert report["metrics"]["context_precision"] == 1.0
    assert report["metrics"]["context_recall"] == 1.0
    assert report["invariants"]["wrong_project_leakage"]["state"] == "pass"
    assert report["cases"][0]["missing_required_ids"] == []
    assert report["cases"][0]["forbidden_selected_ids"] == []
    assert "prompt" not in report["cases"][0]
    assert "content" not in str(report["cases"][0])


def test_regression_comparison_rejects_new_wrong_project_leakage(fixture, task):
    baseline = build_evaluation_report(fixture, [task], [_perfect_result(fixture, task)], suite="test")
    candidate = build_evaluation_report(
        fixture,
        [task],
        [_result(task, [_item(fixture, "mem_promtgen_storage")])],
        suite="test",
    )

    comparison = compare_evaluation_reports(baseline, candidate)

    assert comparison["outcome"] == "regression"
    assert comparison["candidate_gate"]["passed"] is False
    assert comparison["invariant_changes"]["wrong_project_leakage"]["new_failed_case_ids"] == [
        task.task_id
    ]


def test_regression_comparison_marks_safer_quality_improvement(fixture, task):
    baseline = build_evaluation_report(
        fixture,
        [task],
        [_result(task, [_item(fixture, "mem_markdown_source_of_truth")])],
        suite="test",
    )
    candidate = build_evaluation_report(fixture, [task], [_perfect_result(fixture, task)], suite="test")

    comparison = compare_evaluation_reports(baseline, candidate)

    assert comparison["outcome"] == "improved"
    assert comparison["candidate_gate"]["passed"] is True
    assert comparison["metric_deltas"]["context_recall"]["delta"] == 0.5


def test_comparison_refuses_different_corpora(fixture, task):
    report = build_evaluation_report(fixture, [task], [_perfect_result(fixture, task)], suite="dev")
    other_suite = build_evaluation_report(fixture, [task], [_perfect_result(fixture, task)], suite="test")

    with pytest.raises(EvaluationReportError, match="same fixture, suite, and task IDs"):
        compare_evaluation_reports(report, other_suite)


def test_report_writer_refuses_invalid_case_invariant_state(fixture, task, tmp_path):
    report = build_evaluation_report(fixture, [task], [_perfect_result(fixture, task)], suite="dev")
    report["cases"][0]["invariants"]["wrong_project_leakage"] = "unknown"

    with pytest.raises(EvaluationReportError, match="invalid invariant state"):
        write_evaluation_report(tmp_path / "invalid.json", report)
