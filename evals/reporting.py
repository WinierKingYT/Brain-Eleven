"""Deterministic reports and regression comparisons for Phase 15 evaluations.

Reports retain task and memory identifiers, scores, and safety outcomes, but do
not copy task prompts or memory content. That keeps the same contract usable
for public and ignored local-private corpora without duplicating sensitive text.
"""

from __future__ import annotations

import json
import math
import os
import re
import tempfile
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from .contracts import NormalizedEvaluationResult
from .metrics import CaseEvaluation, evaluate_selection
from .schema import GoldenTask, VaultFixture


# Version 1 reports remain readable through the legacy adapter below.  Newly
# generated reports use version 2 so the machine-readable status contract is
# additive and cannot be mistaken for an old, unbound evidence artifact.
EVALUATION_REPORT_SCHEMA_VERSION = 2
LEGACY_EVALUATION_REPORT_SCHEMA_VERSION = 1
EVALUATION_REPORT_TYPE = "brain_eleven_evaluation_report"
REGRESSION_COMPARISON_TYPE = "brain_eleven_evaluation_regression"
_INVARIANT_STATES = frozenset({"pass", "fail", "not_applicable", "unsupported"})
_QUALITY_METRICS = ("context_precision", "context_recall")
_SAFETY_STATES = frozenset({"pass", "fail", "unsupported", "not_applicable"})
_QUALITY_STATES = frozenset({"measured", "unavailable", "not_applicable", "invalid"})
_CAPABILITY_STATES = frozenset({"supported", "unsupported", "not_applicable"})
_EVIDENCE_STATES = frozenset({"verified", "stale", "tampered", "invalid", "unavailable", "legacy"})
_MEASUREMENT_STATES = frozenset({"complete", "incomplete", "blocked"})
_PROMOTION_STATES = frozenset({"eligible", "blocked"})
_STATUS_KEYS = frozenset({
    "schema_version", "safety", "quality", "capabilities", "evidence",
    "measurement", "promotion",
})
_SAFETY_STATUS_KEYS = frozenset({"state", "failed_invariant_codes", "unsupported_capability_codes"})
_QUALITY_STATUS_KEYS = frozenset({"state", "metric_codes"})
_CAPABILITY_KEYS = frozenset({"scope_isolation", "lifecycle_filtering"})
_EVIDENCE_STATUS_KEYS = frozenset({"state", "reason_code"})
_REPORT_TOP_LEVEL_KEYS = frozenset({
    "schema_version", "report_type", "provider", "corpus", "source", "metrics",
    "invariants", "cases", "evaluation_status",
})
_PROVIDER_KEYS = frozenset({"id"})
_CORPUS_KEYS = frozenset({"fixture_id", "suite", "task_count", "task_ids"})
_METRIC_KEYS = frozenset({
    "case_count", "context_precision", "context_recall", "selected_items",
    "relevant_selected_items", "required_items", "required_selected_items",
    "wrong_project_leakage_rate", "forbidden_context_rate",
    "superseded_leakage_rate", "resolved_leakage_rate", "unlabeled_context_rate",
})
_CASE_KEYS = frozenset({
    "task_id", "project_id", "expected", "selected_ids", "missing_required_ids",
    "unexpected_selected_ids", "forbidden_selected_ids", "metrics", "invariants",
    "violations", "passed",
})
_EXPECTED_KEYS = frozenset({"required", "useful", "forbidden"})
_CASE_METRIC_KEYS = frozenset({
    "task_id", "selected_count", "relevant_selected_count", "required_count",
    "required_selected_count", "useful_selected_count", "context_precision",
    "context_recall", "wrong_project_selected_count", "wrong_project_leakage_count",
    "forbidden_context_count", "superseded_selected_count", "superseded_leakage_count",
    "resolved_selected_count", "resolved_leakage_count", "unlabeled_selection_count",
})
# Generic source metadata is deliberately closed, but includes every key used
# by existing Phase 15 callers and by the baseline compatibility wrapper.
_SOURCE_KEYS = frozenset({
    "fixture_seed", "noise_count", "runner", "baseline_id", "source_fingerprint",
    "git_sha", "corpus_version", "evaluator_version", "evaluation_source_fingerprint",
    "seed", "provider_role", "ig01d_role", "suite", "split", "task_count", "task_ids",
    "split_fingerprint",
})
_STATUS_REASON_RE = re.compile(r"^[A-Z0-9][A-Z0-9_.-]{0,63}$")
_SAFE_CODE_RE = re.compile(r"^[a-z0-9][a-z0-9_.-]{0,127}$")
_RAW_KEY_MARKERS = (
    "prompt", "query", "text", "content", "transcript", "message", "raw",
    "secret", "token", "password", "credential", "api_key", "api_secret",
)


class EvaluationReportError(ValueError):
    """Raised when a report is malformed or two reports cannot be compared."""


def _safe_code(value: Any, field: str) -> str:
    if not isinstance(value, str) or not _SAFE_CODE_RE.fullmatch(value):
        raise EvaluationReportError(f"{field} must be a bounded code")
    return value


def _status_codes(values: Iterable[str], field: str) -> list[str]:
    normalized = sorted(set(_safe_code(value, field) for value in values))
    return normalized


def _status_object(
    *,
    safety_state: str,
    failed_codes: Iterable[str] = (),
    unsupported_codes: Iterable[str] = (),
    quality_state: str,
    metric_codes: Iterable[str] = (),
    capabilities: Mapping[str, str],
    evidence_state: str,
    evidence_reason: str,
    measurement: str,
    promotion: str,
) -> dict[str, Any]:
    if safety_state not in _SAFETY_STATES:
        raise EvaluationReportError("evaluation_status.safety.state is invalid")
    if quality_state not in _QUALITY_STATES:
        raise EvaluationReportError("evaluation_status.quality.state is invalid")
    if evidence_state not in _EVIDENCE_STATES:
        raise EvaluationReportError("evaluation_status.evidence.state is invalid")
    if measurement not in _MEASUREMENT_STATES or promotion not in _PROMOTION_STATES:
        raise EvaluationReportError("evaluation_status gate state is invalid")
    if set(capabilities) != _CAPABILITY_KEYS or any(
        value not in _CAPABILITY_STATES for value in capabilities.values()
    ):
        raise EvaluationReportError("evaluation_status.capabilities is invalid")
    if not _STATUS_REASON_RE.fullmatch(evidence_reason):
        raise EvaluationReportError("evaluation_status.evidence.reason_code is invalid")
    return {
        "schema_version": 1,
        "safety": {
            "state": safety_state,
            "failed_invariant_codes": _status_codes(failed_codes, "failed invariant code"),
            "unsupported_capability_codes": _status_codes(unsupported_codes, "unsupported capability code"),
        },
        "quality": {
            "state": quality_state,
            "metric_codes": _status_codes(metric_codes, "metric code"),
        },
        "capabilities": dict(sorted(capabilities.items())),
        "evidence": {"state": evidence_state, "reason_code": evidence_reason},
        "measurement": measurement,
        "promotion": promotion,
    }


def _status_from_evaluations(
    evaluations: Sequence[CaseEvaluation],
    results: Sequence[NormalizedEvaluationResult],
) -> dict[str, Any]:
    summary = _summary_invariants(evaluations)
    failed = [name for name, row in summary.items() if row["state"] == "fail"]
    unsupported = [name for name, row in summary.items() if row["state"] == "unsupported"]
    if failed:
        safety_state = "fail"
    elif unsupported:
        safety_state = "unsupported"
    elif summary and all(row["state"] == "not_applicable" for row in summary.values()):
        safety_state = "not_applicable"
    else:
        safety_state = "pass"
    capabilities: dict[str, str] = {}
    for capability, invariant_names in {
        "scope_isolation": ("wrong_project_leakage",),
        "lifecycle_filtering": ("superseded_lifecycle_leakage", "resolved_lifecycle_leakage"),
    }.items():
        applicable = [
            evaluation for evaluation in evaluations
            if any(evaluation.invariants.get(name) != "not_applicable" for name in invariant_names)
        ]
        if not applicable:
            capabilities[capability] = "not_applicable"
        elif all(_capability_is_supported(result, capability) for result in results):
            capabilities[capability] = "supported"
        else:
            capabilities[capability] = "unsupported"
    metric_codes = [
        name for name in _QUALITY_METRICS
        if any(evaluation.metrics.context_recall is None for evaluation in evaluations)
        if name == "context_recall"
    ]
    quality_state = "unavailable" if metric_codes else "measured"
    # Generic reports intentionally have no provider-specific allowlist. They
    # are useful diagnostics, but cannot be called current evidence.
    return _status_object(
        safety_state=safety_state,
        failed_codes=failed,
        unsupported_codes=[name for name, value in capabilities.items() if value == "unsupported"],
        quality_state=quality_state,
        metric_codes=metric_codes,
        capabilities=capabilities,
        evidence_state="unavailable",
        evidence_reason="GENERIC_SOURCE_ALLOWLIST_UNBOUND",
        measurement="incomplete",
        promotion="blocked",
    )


def _legacy_status(report: Mapping[str, Any]) -> dict[str, Any]:
    invariants = report.get("invariants", {})
    failed = [name for name, value in invariants.items() if isinstance(value, Mapping) and value.get("state") == "fail"]
    unsupported = [name for name, value in invariants.items() if isinstance(value, Mapping) and value.get("state") == "unsupported"]
    safety = "fail" if failed else "unsupported" if unsupported else "pass"
    return _status_object(
        safety_state=safety,
        failed_codes=failed,
        unsupported_codes=unsupported,
        quality_state="measured" if report.get("metrics", {}).get("context_precision") is not None else "unavailable",
        metric_codes=[],
        capabilities={"scope_isolation": "supported", "lifecycle_filtering": "supported"},
        evidence_state="legacy",
        evidence_reason="LEGACY_REPORT_SCHEMA",
        measurement="blocked",
        promotion="blocked",
    )


def _validate_evaluation_status(value: Any, field: str = "evaluation_status") -> dict[str, Any]:
    status = _mapping(value, field)
    if set(status) != _STATUS_KEYS or status.get("schema_version") != 1:
        raise EvaluationReportError(f"{field} has an invalid schema")
    safety = _mapping(status.get("safety"), f"{field}.safety")
    if set(safety) != _SAFETY_STATUS_KEYS or safety.get("state") not in _SAFETY_STATES:
        raise EvaluationReportError(f"{field}.safety is invalid")
    quality = _mapping(status.get("quality"), f"{field}.quality")
    if set(quality) != _QUALITY_STATUS_KEYS or quality.get("state") not in _QUALITY_STATES:
        raise EvaluationReportError(f"{field}.quality is invalid")
    for key in ("failed_invariant_codes", "unsupported_capability_codes"):
        values = safety.get(key)
        if not isinstance(values, list) or values != sorted(set(values)):
            raise EvaluationReportError(f"{field}.safety.{key} is invalid")
        for code in values:
            _safe_code(code, f"{field}.safety.{key}")
    values = quality.get("metric_codes")
    if not isinstance(values, list) or values != sorted(set(values)):
        raise EvaluationReportError(f"{field}.quality.metric_codes is invalid")
    for code in values:
        _safe_code(code, f"{field}.quality.metric_codes")
    capabilities = _mapping(status.get("capabilities"), f"{field}.capabilities")
    if set(capabilities) != _CAPABILITY_KEYS or any(value not in _CAPABILITY_STATES for value in capabilities.values()):
        raise EvaluationReportError(f"{field}.capabilities is invalid")
    evidence = _mapping(status.get("evidence"), f"{field}.evidence")
    if set(evidence) != _EVIDENCE_STATUS_KEYS or evidence.get("state") not in _EVIDENCE_STATES:
        raise EvaluationReportError(f"{field}.evidence is invalid")
    reason = evidence.get("reason_code")
    if not isinstance(reason, str) or not _STATUS_REASON_RE.fullmatch(reason):
        raise EvaluationReportError(f"{field}.evidence.reason_code is invalid")
    if status.get("measurement") not in _MEASUREMENT_STATES or status.get("promotion") not in _PROMOTION_STATES:
        raise EvaluationReportError(f"{field} gate states are invalid")
    return dict(status)


def _walk_content_free(value: Any, path: str = "report") -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            if not isinstance(key, str) or not key.strip():
                raise EvaluationReportError(f"{path} has an invalid key")
            lowered = key.strip().lower()
            if (
                lowered in _RAW_KEY_MARKERS
                or lowered.startswith(("raw", "secret", "token", "password", "credential"))
                or any(marker in lowered for marker in ("prompt", "transcript", "api_key", "api_secret"))
            ):
                raise EvaluationReportError(f"{path}.{key} is not content-free")
            _walk_content_free(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _walk_content_free(child, f"{path}[{index}]")


def _capability_is_supported(result: NormalizedEvaluationResult, capability: str) -> bool:
    return result.capabilities.get(capability) == "supported"


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
        if normalized_key not in _SOURCE_KEYS:
            raise EvaluationReportError(f"source.{normalized_key} is not an allowed field")
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
        "evaluation_status": _status_from_evaluations(evaluations, [result_by_id[task_id] for task_id in task_ids]),
    }


def _validate_report(report: Mapping[str, Any]) -> dict[str, Any]:
    """Validate the report fields needed for safe persistence and comparison."""

    report = _mapping(report, "report")
    _walk_content_free(report)
    schema_version = report.get("schema_version")
    legacy = schema_version == LEGACY_EVALUATION_REPORT_SCHEMA_VERSION
    if schema_version not in {LEGACY_EVALUATION_REPORT_SCHEMA_VERSION, EVALUATION_REPORT_SCHEMA_VERSION}:
        raise EvaluationReportError("report schema_version is unsupported")
    allowed_top_level = _REPORT_TOP_LEVEL_KEYS - ({"evaluation_status"} if legacy else set())
    unknown = sorted(set(report) - allowed_top_level)
    if unknown:
        raise EvaluationReportError(f"report contains unknown fields: {', '.join(unknown)}")
    if report.get("report_type") != EVALUATION_REPORT_TYPE:
        raise EvaluationReportError("unsupported report_type")
    provider = _mapping(report.get("provider"), "report.provider")
    if set(provider) != _PROVIDER_KEYS:
        raise EvaluationReportError("report.provider contains unknown fields")
    _nonempty_string(provider.get("id"), "report.provider.id")
    corpus = _mapping(report.get("corpus"), "report.corpus")
    if set(corpus) != _CORPUS_KEYS:
        raise EvaluationReportError("report.corpus contains unknown fields")
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
    if set(metrics) != _METRIC_KEYS:
        raise EvaluationReportError("report.metrics contains unknown or missing fields")
    if metrics.get("case_count") != len(task_ids):
        raise EvaluationReportError("report.metrics.case_count must match task_ids")
    for name, value in metrics.items():
        if name == "case_count" or name.endswith("_items"):
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise EvaluationReportError(f"report.metrics.{name} must be a non-negative integer")
        else:
            _finite_number(value, f"report.metrics.{name}", nullable=name in _QUALITY_METRICS)
    invariants = _mapping(report.get("invariants"), "report.invariants")
    if not invariants:
        raise EvaluationReportError("report.invariants must not be empty")
    for name, summary_value in invariants.items():
        _nonempty_string(name, "invariant name")
        summary = _mapping(summary_value, f"report.invariants.{name}")
        if set(summary) != {"state", "failed_case_ids", "unsupported_case_ids", "not_applicable_case_ids"}:
            raise EvaluationReportError(f"report.invariants.{name} contains unknown or missing fields")
        if summary.get("state") not in _INVARIANT_STATES:
            raise EvaluationReportError(f"report.invariants.{name}.state is invalid")
        for key in ("failed_case_ids", "unsupported_case_ids", "not_applicable_case_ids"):
            values = summary.get(key)
            if not isinstance(values, list) or values != sorted(set(values)) or any(
                not isinstance(value, str) or not value for value in values
            ):
                raise EvaluationReportError(f"report.invariants.{name}.{key} must be sorted")

    cases = report.get("cases")
    if not isinstance(cases, list) or len(cases) != len(task_ids):
        raise EvaluationReportError("report.cases must contain exactly one entry per task")
    if [case.get("task_id") if isinstance(case, Mapping) else None for case in cases] != task_ids:
        raise EvaluationReportError("report.cases must be ordered by task_id")
    invariant_names = set(invariants)
    for case in cases:
        task_id = case.get("task_id") if isinstance(case, Mapping) else "unknown"
        if not isinstance(case, Mapping) or set(case) != _CASE_KEYS:
            raise EvaluationReportError(f"report case {task_id} contains unknown or missing fields")
        if not isinstance(case.get("project_id"), (str, type(None))):
            raise EvaluationReportError(f"report case {task_id}.project_id is invalid")
        for key in ("expected",):
            nested = _mapping(case.get(key), f"report case {task_id}.{key}")
            if set(nested) != _EXPECTED_KEYS:
                raise EvaluationReportError(f"report case {task_id}.{key} contains unknown fields")
            for value in nested.values():
                if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
                    raise EvaluationReportError(f"report case {task_id}.{key} must contain identifier arrays")
        for key in ("selected_ids", "missing_required_ids", "unexpected_selected_ids", "forbidden_selected_ids"):
            values = case.get(key)
            if not isinstance(values, list) or any(not isinstance(value, str) for value in values):
                raise EvaluationReportError(f"report case {task_id}.{key} must contain identifiers")
        case_metrics = _mapping(case.get("metrics"), f"report case {task_id}.metrics")
        if set(case_metrics) != _CASE_METRIC_KEYS:
            raise EvaluationReportError(f"report case {task_id}.metrics contains unknown or missing fields")
        for name, value in case_metrics.items():
            if name == "task_id":
                if value != task_id:
                    raise EvaluationReportError(f"report case {task_id}.metrics.task_id does not match")
            elif name == "context_recall":
                _finite_number(value, f"report case {task_id}.metrics.{name}", nullable=True)
            elif name == "context_precision":
                _finite_number(value, f"report case {task_id}.metrics.{name}")
            elif isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise EvaluationReportError(f"report case {task_id}.metrics.{name} must be non-negative integer")
        case_invariants = _mapping(case.get("invariants"), f"report case {task_id} invariants")
        if set(case_invariants) != invariant_names:
            raise EvaluationReportError(
                f"report case {task_id} invariants must match report invariants"
            )
        if any(state not in _INVARIANT_STATES for state in case_invariants.values()):
            raise EvaluationReportError(f"report case {task_id} has an invalid invariant state")
        violations = case.get("violations")
        if not isinstance(violations, list) or violations != sorted(set(violations)) or any(
            name not in invariant_names for name in violations
        ):
            raise EvaluationReportError(f"report case {task_id}.violations is invalid")
        if not isinstance(case.get("passed"), bool):
            raise EvaluationReportError(f"report case {task_id}.passed must be boolean")
        expected_passed = not any(state in {"fail", "unsupported"} for state in case_invariants.values())
        if case.get("passed") != expected_passed:
            raise EvaluationReportError(f"report case {task_id}.passed hides a safety state")
    normalized = dict(report)
    if legacy:
        # Do not rewrite historical JSON on disk, but expose its status through
        # a read-only adapter so callers cannot mistake it for current evidence.
        normalized["evaluation_status"] = _legacy_status(report)
    else:
        _validate_evaluation_status(report.get("evaluation_status"))
    return normalized


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

    candidate_status = candidate.get("evaluation_status", _legacy_status(candidate))
    baseline_status = baseline.get("evaluation_status", _legacy_status(baseline))
    _validate_evaluation_status(candidate_status)
    _validate_evaluation_status(baseline_status)
    candidate_quality = candidate_status["quality"]
    candidate_evidence = candidate_status["evidence"]
    candidate_promotion = (
        "eligible"
        if candidate_quality["state"] == "measured"
        and candidate_evidence["state"] == "verified"
        and candidate_status["safety"]["state"] == "pass"
        else "blocked"
    )

    return {
        # Comparison metadata has its own frozen schema; report status version
        # migration must not reinterpret the existing V1/V2 comparison shape.
        "schema_version": 1,
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
        "evaluation_status": {
            "baseline": {
                "quality": baseline_status["quality"]["state"],
                "evidence": baseline_status["evidence"]["state"],
                "promotion": baseline_status["promotion"],
            },
            "candidate": {
                "quality": candidate_quality["state"],
                "evidence": candidate_evidence["state"],
                "promotion": candidate_promotion,
            },
        },
        "quality_status": candidate_quality["state"],
        "evidence_status": candidate_evidence["state"],
        "promotion_status": candidate_promotion,
        "outcome": outcome,
    }
