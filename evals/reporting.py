"""Deterministic reports and regression comparisons for Phase 15 evaluations.

Reports retain task and memory identifiers, scores, and safety outcomes, but do
not copy task prompts or memory content. That keeps the same contract usable
for public and ignored local-private corpora without duplicating sensitive text.
"""

from __future__ import annotations

import json
import math
import os
import tempfile
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from .contracts import NormalizedEvaluationResult
from .metrics import CaseEvaluation, evaluate_selection
from .schema import GoldenTask, VaultFixture


EVALUATION_REPORT_SCHEMA_VERSION = 1
EVALUATION_REPORT_TYPE = "brain_eleven_evaluation_report"
REGRESSION_COMPARISON_TYPE = "brain_eleven_evaluation_regression"
_INVARIANT_STATES = frozenset({"pass", "fail", "not_applicable", "unsupported"})
_QUALITY_METRICS = ("context_precision", "context_recall")


class EvaluationReportError(ValueError):
    """Raised when a report is malformed or two reports cannot be compared."""


def _nonempty_string(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise EvaluationReportError(f"{field_name} must be a non-empty string")
    return value.strip()


def _mapping(value: Any, field_name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise EvaluationReportError(f"{field_name} must be an object")
    return value


def _finite_number(value: Any, field_name: str, *, nullable: bool = False) -> float | None:
    if value is None and nullable:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise EvaluationReportError(f"{field_name} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise EvaluationReportError(f"{field_name} must be finite")
    return result


def _sorted_task_ids(tasks: Iterable[GoldenTask]) -> tuple[str, ...]:
    task_ids = tuple(sorted(task.task_id for task in tasks))
    if not task_ids:
        raise EvaluationReportError("a report requires at least one task")
    if len(task_ids) != len(set(task_ids)):
        raise EvaluationReportError("task IDs must be unique")
    return task_ids


def _safe_source(source: Mapping[str, Any] | None) -> dict[str, Any]:
    if source is None:
        return {}
    source = _mapping(source, "source")
    normalized: dict[str, Any] = {}
    for key, value in source.items():
        normalized_key = _nonempty_string(key, "source key")
        if not isinstance(value, (str, int, float, bool)) and value is not None:
            raise EvaluationReportError(f"source.{normalized_key} must be a JSON scalar")
        if isinstance(value, float) and not math.isfinite(value):
            raise EvaluationReportError(f"source.{normalized_key} must be finite")
        normalized[normalized_key] = value
    return dict(sorted(normalized.items()))


def _case_payload(task: GoldenTask, evaluation: CaseEvaluation) -> dict[str, Any]:
    selected_ids = evaluation.selected_ids
    selected_id_set = frozenset(selected_ids)
    required = tuple(task.required)
    useful = tuple(task.useful)
    forbidden = tuple(task.forbidden)
    relevant = frozenset(required) | frozenset(useful)
    return {
        "task_id": task.task_id,
        "project_id": task.project_id,
        "expected": {
            "required": list(required),
            "useful": list(useful),
            "forbidden": list(forbidden),
        },
        "selected_ids": list(selected_ids),
        "missing_required_ids": [memory_id for memory_id in required if memory_id not in selected_id_set],
        "unexpected_selected_ids": [
            memory_id for memory_id in selected_ids if memory_id not in relevant
        ],
        "forbidden_selected_ids": [
            memory_id for memory_id in selected_ids if memory_id in frozenset(forbidden)
        ],
        "metrics": evaluation.metrics.as_dict(),
        "invariants": dict(evaluation.invariants),
        "violations": list(evaluation.violations),
        "passed": evaluation.passed,
    }


def _average(values: Sequence[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _summary_metrics(evaluations: Sequence[CaseEvaluation]) -> dict[str, float | int | None]:
    if not evaluations:
        raise EvaluationReportError("a report requires at least one case evaluation")
    metrics = [evaluation.metrics for evaluation in evaluations]
    selected_count = sum(item.selected_count for item in metrics)
    return {
        "case_count": len(metrics),
        "context_precision": _average([item.context_precision for item in metrics]),
        "context_recall": _average(
            [item.context_recall for item in metrics if item.context_recall is not None]
        ),
        "selected_items": selected_count,
        "relevant_selected_items": sum(item.relevant_selected_count for item in metrics),
        "required_items": sum(item.required_count for item in metrics),
        "required_selected_items": sum(item.required_selected_count for item in metrics),
        "wrong_project_leakage_rate": sum(
            item.wrong_project_leakage_count > 0 for item in metrics
        ) / len(metrics),
        "forbidden_context_rate": sum(item.forbidden_context_count > 0 for item in metrics)
        / len(metrics),
        "superseded_leakage_rate": sum(item.superseded_leakage_count > 0 for item in metrics)
        / len(metrics),
        "resolved_leakage_rate": sum(item.resolved_leakage_count > 0 for item in metrics)
        / len(metrics),
        "unlabeled_context_rate": (
            sum(item.unlabeled_selection_count for item in metrics) / selected_count
            if selected_count
            else 0.0
        ),
    }


def _summary_invariants(evaluations: Sequence[CaseEvaluation]) -> dict[str, dict[str, Any]]:
    all_names = sorted({name for evaluation in evaluations for name in evaluation.invariants})
    summary: dict[str, dict[str, Any]] = {}
    for name in all_names:
        outcomes = {
            evaluation.metrics.task_id: evaluation.invariants.get(name, "unsupported")
            for evaluation in evaluations
        }
        failed = sorted(task_id for task_id, state in outcomes.items() if state == "fail")
        unsupported = sorted(task_id for task_id, state in outcomes.items() if state == "unsupported")
        not_applicable = sorted(
            task_id for task_id, state in outcomes.items() if state == "not_applicable"
        )
        if failed:
            state = "fail"
        elif unsupported:
            state = "unsupported"
        elif len(not_applicable) == len(outcomes):
            state = "not_applicable"
        else:
            state = "pass"
        summary[name] = {
            "state": state,
            "failed_case_ids": failed,
            "unsupported_case_ids": unsupported,
            "not_applicable_case_ids": not_applicable,
        }
    return summary


def build_evaluation_report(
    fixture: VaultFixture,
    tasks: Sequence[GoldenTask],
    results: Sequence[NormalizedEvaluationResult],
    *,
    suite: str,
    source: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build one deterministic report from a fixture, suite tasks, and results."""

    suite = _nonempty_string(suite, "suite")
    task_ids = _sorted_task_ids(tasks)
    task_by_id = {task.task_id: task for task in tasks}
    result_by_id = {result.task_id: result for result in results}
    if len(result_by_id) != len(results):
        raise EvaluationReportError("result task IDs must be unique")
    if set(result_by_id) != set(task_by_id):
        missing = sorted(set(task_by_id) - set(result_by_id))
        unexpected = sorted(set(result_by_id) - set(task_by_id))
        raise EvaluationReportError(f"results do not match tasks; missing={missing}, unexpected={unexpected}")
    provider_ids = {result.provider_id for result in results}
    if len(provider_ids) != 1:
        raise EvaluationReportError("one report must contain exactly one provider")

    evaluations: list[CaseEvaluation] = []
    cases: list[dict[str, Any]] = []
    for task_id in task_ids:
        task = task_by_id[task_id]
        evaluation = evaluate_selection(task, fixture, result_by_id[task_id])
        evaluations.append(evaluation)
        cases.append(_case_payload(task, evaluation))

    return {
        "schema_version": EVALUATION_REPORT_SCHEMA_VERSION,
        "report_type": EVALUATION_REPORT_TYPE,
        "provider": {"id": provider_ids.pop()},
        "corpus": {
            "fixture_id": fixture.fixture_id,
            "suite": suite,
            "task_count": len(task_ids),
            "task_ids": list(task_ids),
        },
        "source": _safe_source(source),
        "metrics": _summary_metrics(evaluations),
        "invariants": _summary_invariants(evaluations),
        "cases": cases,
    }


def _validate_report(report: Mapping[str, Any]) -> dict[str, Any]:
    """Validate the report fields needed for safe persistence and comparison."""

    report = _mapping(report, "report")
    if report.get("schema_version") != EVALUATION_REPORT_SCHEMA_VERSION:
        raise EvaluationReportError(
            f"report schema_version must be {EVALUATION_REPORT_SCHEMA_VERSION}"
        )
    if report.get("report_type") != EVALUATION_REPORT_TYPE:
        raise EvaluationReportError("unsupported report_type")
    provider = _mapping(report.get("provider"), "report.provider")
    _nonempty_string(provider.get("id"), "report.provider.id")
    corpus = _mapping(report.get("corpus"), "report.corpus")
    _nonempty_string(corpus.get("fixture_id"), "report.corpus.fixture_id")
    _nonempty_string(corpus.get("suite"), "report.corpus.suite")
    task_ids = corpus.get("task_ids")
    if not isinstance(task_ids, list) or not task_ids:
        raise EvaluationReportError("report.corpus.task_ids must be a non-empty array")
    if any(not isinstance(task_id, str) or not task_id for task_id in task_ids):
        raise EvaluationReportError("report.corpus.task_ids must contain non-empty strings")
    if len(task_ids) != len(set(task_ids)) or task_ids != sorted(task_ids):
        raise EvaluationReportError("report.corpus.task_ids must be unique and sorted")
    if corpus.get("task_count") != len(task_ids):
        raise EvaluationReportError("report.corpus.task_count must match task_ids")
    _safe_source(report.get("source"))

    metrics = _mapping(report.get("metrics"), "report.metrics")
    if metrics.get("case_count") != len(task_ids):
        raise EvaluationReportError("report.metrics.case_count must match task_ids")
    for name in _QUALITY_METRICS:
        _finite_number(metrics.get(name), f"report.metrics.{name}", nullable=True)
    invariants = _mapping(report.get("invariants"), "report.invariants")
    for name, summary_value in invariants.items():
        _nonempty_string(name, "invariant name")
        summary = _mapping(summary_value, f"report.invariants.{name}")
        if summary.get("state") not in _INVARIANT_STATES:
            raise EvaluationReportError(f"report.invariants.{name}.state is invalid")
        for key in ("failed_case_ids", "unsupported_case_ids", "not_applicable_case_ids"):
            values = summary.get(key)
            if not isinstance(values, list) or values != sorted(values):
                raise EvaluationReportError(f"report.invariants.{name}.{key} must be sorted")

    cases = report.get("cases")
    if not isinstance(cases, list) or len(cases) != len(task_ids):
        raise EvaluationReportError("report.cases must contain exactly one entry per task")
    if [case.get("task_id") if isinstance(case, Mapping) else None for case in cases] != task_ids:
        raise EvaluationReportError("report.cases must be ordered by task_id")
    invariant_names = set(invariants)
    for case in cases:
        case_invariants = _mapping(case.get("invariants"), f"report case {case['task_id']} invariants")
        if set(case_invariants) != invariant_names:
            raise EvaluationReportError(
                f"report case {case['task_id']} invariants must match report invariants"
            )
        if any(state not in _INVARIANT_STATES for state in case_invariants.values()):
            raise EvaluationReportError(f"report case {case['task_id']} has an invalid invariant state")
    return dict(report)


def _atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        descriptor, temporary_name = tempfile.mkstemp(
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
        )
        temporary_path = Path(temporary_name)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        temporary_path.replace(path)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()


def write_evaluation_report(path: Path | str, report: Mapping[str, Any]) -> None:
    """Validate and atomically write an evaluation report."""

    payload = _validate_report(report)
    _atomic_write_json(Path(path), payload)


def read_evaluation_report(path: Path | str) -> dict[str, Any]:
    """Read and validate an existing report before it drives a comparison."""

    report_path = Path(path)
    try:
        loaded = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise EvaluationReportError(f"cannot read evaluation report {report_path}: {error}") from error
    return _validate_report(loaded)


def _case_invariants(report: Mapping[str, Any]) -> dict[str, dict[str, str]]:
    return {
        case["task_id"]: dict(case["invariants"])
        for case in report["cases"]
    }


def compare_evaluation_reports(
    baseline: Mapping[str, Any],
    candidate: Mapping[str, Any],
) -> dict[str, Any]:
    """Compare compatible reports and reject any new safety-gate failure."""

    baseline = _validate_report(baseline)
    candidate = _validate_report(candidate)
    baseline_corpus = baseline["corpus"]
    candidate_corpus = candidate["corpus"]
    if (
        baseline_corpus["fixture_id"] != candidate_corpus["fixture_id"]
        or baseline_corpus["suite"] != candidate_corpus["suite"]
        or baseline_corpus["task_ids"] != candidate_corpus["task_ids"]
    ):
        raise EvaluationReportError("reports must use the same fixture, suite, and task IDs")

    metric_deltas: dict[str, dict[str, float | None]] = {}
    for name in _QUALITY_METRICS:
        before = _finite_number(baseline["metrics"].get(name), f"baseline {name}", nullable=True)
        after = _finite_number(candidate["metrics"].get(name), f"candidate {name}", nullable=True)
        metric_deltas[name] = {
            "baseline": before,
            "candidate": after,
            "delta": after - before if before is not None and after is not None else None,
        }

    baseline_cases = _case_invariants(baseline)
    candidate_cases = _case_invariants(candidate)
    invariant_changes: dict[str, dict[str, list[str]]] = {}
    names = sorted(
        set(baseline["invariants"]) | set(candidate["invariants"])
    )
    has_safety_regression = False
    for name in names:
        before_failures = {
            task_id for task_id, states in baseline_cases.items() if states.get(name) == "fail"
        }
        after_failures = {
            task_id for task_id, states in candidate_cases.items() if states.get(name) == "fail"
        }
        before_unsupported = {
            task_id for task_id, states in baseline_cases.items() if states.get(name) == "unsupported"
        }
        after_unsupported = {
            task_id for task_id, states in candidate_cases.items() if states.get(name) == "unsupported"
        }
        new_failures = sorted(after_failures - before_failures)
        new_unsupported = sorted(after_unsupported - before_unsupported)
        if new_failures or new_unsupported:
            has_safety_regression = True
        invariant_changes[name] = {
            "new_failed_case_ids": new_failures,
            "resolved_failed_case_ids": sorted(before_failures - after_failures),
            "new_unsupported_case_ids": new_unsupported,
            "resolved_unsupported_case_ids": sorted(before_unsupported - after_unsupported),
        }

    candidate_failures = {
        name: summary["failed_case_ids"]
        for name, summary in candidate["invariants"].items()
        if summary["failed_case_ids"]
    }
    candidate_unsupported = {
        name: summary["unsupported_case_ids"]
        for name, summary in candidate["invariants"].items()
        if summary["unsupported_case_ids"]
    }
    gate_passed = not candidate_failures and not candidate_unsupported
    quality_deltas = [
        values["delta"] for values in metric_deltas.values() if values["delta"] is not None
    ]
    if has_safety_regression or not gate_passed:
        outcome = "regression"
    elif any(delta > 0 for delta in quality_deltas) and not any(delta < 0 for delta in quality_deltas):
        outcome = "improved"
    elif any(delta < 0 for delta in quality_deltas) and not any(delta > 0 for delta in quality_deltas):
        outcome = "degraded"
    elif any(delta != 0 for delta in quality_deltas):
        outcome = "mixed"
    else:
        outcome = "unchanged"

    return {
        "schema_version": EVALUATION_REPORT_SCHEMA_VERSION,
        "comparison_type": REGRESSION_COMPARISON_TYPE,
        "baseline": {"provider_id": baseline["provider"]["id"]},
        "candidate": {"provider_id": candidate["provider"]["id"]},
        "corpus": {
            "fixture_id": baseline_corpus["fixture_id"],
            "suite": baseline_corpus["suite"],
            "task_count": baseline_corpus["task_count"],
        },
        "metric_deltas": metric_deltas,
        "invariant_changes": invariant_changes,
        "candidate_gate": {
            "passed": gate_passed,
            "failed_invariants": candidate_failures,
            "unsupported_invariants": candidate_unsupported,
        },
        "outcome": outcome,
    }
