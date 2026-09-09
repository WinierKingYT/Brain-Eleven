"""Deterministic, production-independent IG01-C evaluation engine."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
import json
import math
import os
from pathlib import Path
import tempfile
from typing import Any

from .contracts import (
    ALL_GATES,
    EVALUATOR_VERSION,
    HARD_ZERO_GATES,
    REPORT_SCHEMA_VERSION,
    EvaluationContractError,
    MetricValue,
    SafetyEvent,
)
from .metrics import (
    _case_id,
    _ids,
    _metric_map,
    _nonnegative_int,
    _ratio,
    aggregate_metric_values,
    evaluate_capture_case,
    evaluate_context_case,
    evaluate_extraction_case,
    evaluate_lifecycle_case,
    evaluate_reference_case,
    evaluate_retrieval_case,
    expected_calibration_error,
    gate_summary,
)


class EvaluatorError(EvaluationContractError):
    """Raised when a corpus/output collection cannot be scored safely."""


_BANNED_REPORT_KEYS = frozenset({
    "prompt", "query", "text", "content", "transcript", "raw_prompt", "raw_text",
    "raw_transcript", "memory_content", "message", "free_text", "diagnostic", "details",
    "token", "tokens", "secret", "secrets", "api_key", "api_secret", "password",
    "credential", "credentials", "raw", "token_count",
})


def _safe_scalar(value: Any, field: str) -> Any:
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise EvaluatorError(f"{field} must be finite")
        return value
    raise EvaluatorError(f"{field} must be a JSON scalar")


def _safe_source(source: Mapping[str, Any] | None) -> dict[str, Any]:
    if source is None:
        return {}
    if not isinstance(source, Mapping):
        raise EvaluatorError("source must be an object")
    normalized: dict[str, Any] = {}
    for key, value in source.items():
        if not isinstance(key, str) or not key.strip():
            raise EvaluatorError("source keys must be non-empty strings")
        lowered = key.lower()
        if lowered in _BANNED_REPORT_KEYS or any(
            marker in lowered for marker in ("secret", "password", "credential", "api_key")
        ):
            raise EvaluatorError(f"source.{key} cannot contain raw content")
        normalized[key.strip()] = _safe_scalar(value, f"source.{key}")
    return dict(sorted(normalized.items()))


def _output_mapping(output: Any, field: str) -> Mapping[str, Any]:
    if not isinstance(output, Mapping):
        raise EvaluatorError(f"{field} must be an object")
    return output


def _abstention_case(case: Mapping[str, Any], output: Any) -> dict[str, Any]:
    case_id = _case_id(case)
    value = _output_mapping(output, "abstention output")
    status = str(value.get("status", "NO_TARGET")).strip().upper().replace("-", "_").replace(" ", "_")
    safe_statuses = {"AMBIGUOUS", "NO_TARGET", "REVIEW_REQUIRED", "ABSTAIN"}
    correct = status in safe_statuses and not value.get("target_id") and not value.get("target")
    metric = _ratio(1 if correct else 0, 1)
    events: list[SafetyEvent] = []
    if not correct:
        events.append(SafetyEvent("cross_project_target", case_id, "unanswerable_case_not_abstained"))
    return {
        "case_id": case_id,
        "family": "reference_resolution",
        "metrics": {"answerability_abstention_rate": metric.as_dict()},
        "safety_events": [event.as_dict() for event in events],
        "violations": sorted({event.gate for event in events}),
        "gate_denominators": {},
        "passed": not events,
    }


def evaluate_case(
    case: Mapping[str, Any],
    output: Any,
    *,
    retrieval_k: int = 5,
    token_counts: Mapping[str, int] | None = None,
) -> dict[str, Any]:
    """Dispatch one immutable case to a pure family evaluator."""

    if not isinstance(case, Mapping):
        raise EvaluatorError("case must be an object")
    family = str(case.get("family", "")).strip().lower()
    answerability = case.get("answerability")
    if isinstance(answerability, Mapping) and answerability.get("status") == "unanswerable":
        return _abstention_case(case, output)
    if case.get("case_kind") == "abstention":
        return _abstention_case(case, output)
    if family == "retrieval":
        if isinstance(output, Mapping):
            retrieved = output.get("retrieved_ids", output.get("selected_ids", []))
            item_case = dict(case)
            if "candidate_metadata" not in item_case and "items" in output:
                item_case["candidate_metadata"] = output["items"]
        else:
            retrieved = output
            item_case = case
        return evaluate_retrieval_case(item_case, retrieved, k=retrieval_k, token_counts=token_counts)
    if family == "context_compilation":
        if isinstance(output, Mapping):
            selected = output.get("selected_ids", output.get("retrieved_ids", []))
        else:
            selected = output
        return evaluate_context_case(case, selected, token_counts=token_counts)
    if family == "extraction":
        return evaluate_extraction_case(case, output)
    if family == "reference_resolution":
        return evaluate_reference_case(case, output)
    if family == "lifecycle":
        return evaluate_lifecycle_case(case, output)
    if family == "capture":
        return evaluate_capture_case(case, output)
    if family == "safety":
        value = _output_mapping(output, "safety output")
        case_id = _case_id(case)
        raw_violations = value.get("violations", [])
        if not isinstance(raw_violations, Sequence) or isinstance(raw_violations, (str, bytes)):
            raise EvaluatorError("safety violations must be an array")
        events = []
        for gate in raw_violations:
            if gate not in ALL_GATES:
                raise EvaluatorError(f"unknown safety violation: {gate}")
            events.append(SafetyEvent(gate, case_id, "reported_safety_violation"))
        return {
            "case_id": case_id,
            "family": "safety",
            "metrics": {"safety_clean": _ratio(1 if not events else 0, 1).as_dict()},
            "safety_events": [event.as_dict() for event in events],
            "violations": sorted({event.gate for event in events}),
            "gate_denominators": {},
            "passed": not events,
        }
    raise EvaluatorError(f"unsupported evaluation family: {family!r}")


def _metric_from_dict(value: Mapping[str, Any]) -> MetricValue:
    if not isinstance(value, Mapping):
        raise EvaluatorError("metric value must be an object")
    return MetricValue(
        value=value.get("value"),
        numerator=value.get("numerator", 0),
        denominator=value.get("denominator", 0),
        not_applicable=bool(value.get("not_applicable", False)),
        empty_selection=bool(value.get("empty_selection", False)),
    )


_POOLED_METRICS = frozenset({
    "capture_loss_rate",
    "duplicate_canonical_effect_rate",
    "replay_correctness",
    "terminal_effect_agreement",
    "lifecycle_transition_safety",
    "false_supersession_rate",
})


def _aggregate_metrics(case_results: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    by_family: dict[str, dict[str, list[MetricValue]]] = defaultdict(lambda: defaultdict(list))
    for result in case_results:
        family = str(result["family"])
        metrics = result.get("metrics", {})
        if not isinstance(metrics, Mapping):
            raise EvaluatorError("case metrics must be an object")
        for name, value in metrics.items():
            by_family[family][name].append(_metric_from_dict(value))
    aggregate: dict[str, dict[str, Any]] = {}
    for family, values in sorted(by_family.items()):
        aggregate[family] = {}
        for name, metrics in sorted(values.items()):
            if family == "extraction" and name == "ece":
                samples = [
                    (float(result["ece_sample"]["confidence"]), bool(result["ece_sample"]["correct"]))
                    for result in case_results
                    if result.get("family") == "extraction" and result.get("ece_sample") is not None
                ]
                aggregate[family][name] = expected_calibration_error(samples).as_dict()
            else:
                pooled = name in _POOLED_METRICS
                aggregate[family][name] = aggregate_metric_values(metrics, pooled=pooled).as_dict()
    return aggregate


def _control_case(case: Mapping[str, Any], *, k: int, token_counts: Mapping[str, int] | None) -> dict[str, Any]:
    candidate_ids = _ids(case.get("candidate_ids", []), "case.candidate_ids")
    all_result = evaluate_retrieval_case(
        case,
        tuple(sorted(candidate_ids)),
        k=max(k, len(candidate_ids)),
        token_counts=token_counts,
    )
    none_result = evaluate_retrieval_case(case, (), k=0, token_counts=token_counts)
    return {
        "select_all": {
            "case_id": all_result["case_id"],
            "metrics": all_result["metrics"],
            "violations": all_result["violations"],
        },
        "select_none": {
            "case_id": none_result["case_id"],
            "metrics": none_result["metrics"],
            "violations": none_result["violations"],
        },
    }


def _validate_benchmark_population(
    cases: Sequence[Mapping[str, Any]],
    results: Sequence[Mapping[str, Any]],
) -> None:
    """Reject release reports that do not contain measurable populations."""

    scored = [
        case for case in cases
        if not (
            isinstance(case.get("answerability"), Mapping)
            and case["answerability"].get("status") == "unanswerable"
        )
        and case.get("case_kind") != "abstention"
    ]
    if not scored:
        raise EvaluatorError("INVALID_BENCHMARK_RUN: no answerable cases")
    by_family_language: dict[tuple[str, str], int] = defaultdict(int)
    for case in scored:
        family = str(case.get("family", "")).strip().lower()
        language = str(case.get("language", "unknown")).strip().lower() or "unknown"
        by_family_language[(family, language)] += 1
    undersized = [key for key, count in by_family_language.items() if count < 5]
    if undersized:
        raise EvaluatorError(
            "INVALID_BENCHMARK_RUN: fewer than five answerable cases per family/language: "
            + ", ".join(f"{family}/{language}" for family, language in sorted(undersized))
        )
    for result in results:
        metrics = result.get("metrics", {})
        for name, raw_metric in metrics.items():
            metric = _metric_from_dict(raw_metric)
            if metric.not_applicable:
                continue
            if metric.empty_selection:
                continue
            if metric.denominator <= 0:
                raise EvaluatorError(
                    f"INVALID_BENCHMARK_RUN: metric {name} has no positive denominator"
                )


def evaluate_corpus(
    cases: Sequence[Mapping[str, Any]],
    outputs: Mapping[str, Any],
    *,
    corpus_version: str,
    split: str,
    retrieval_k: int = 5,
    seed: int = 0,
    source_fingerprint: str = "",
    git_sha: str = "",
    include_controls: bool = True,
    enforce_benchmark: bool = True,
) -> dict[str, Any]:
    """Evaluate a fixed collection and return a content-free report.

    ``outputs`` is keyed by case ID.  Missing or unexpected IDs are rejected so
    a caller cannot silently drop difficult cases.  Holdout labels are never
    modified or returned; only stable case and memory IDs are emitted.
    """

    if not isinstance(cases, Sequence) or isinstance(cases, (str, bytes)) or not cases:
        raise EvaluatorError("cases must be a non-empty sequence")
    if not isinstance(outputs, Mapping):
        raise EvaluatorError("outputs must be an object keyed by case_id")
    corpus_version = str(corpus_version).strip()
    split = str(split).strip().lower()
    if not corpus_version or not split:
        raise EvaluatorError("corpus_version and split are required")
    if include_controls is False:
        raise EvaluatorError("select_all/select_none controls are mandatory")
    retrieval_k = _nonnegative_int(retrieval_k, "retrieval_k")
    seed = _nonnegative_int(seed, "seed")
    case_ids = tuple(_case_id(case) for case in cases)
    if len(case_ids) != len(set(case_ids)):
        raise EvaluatorError("case IDs must be unique")
    if set(outputs) != set(case_ids):
        missing = sorted(set(case_ids) - set(outputs))
        unexpected = sorted(set(outputs) - set(case_ids))
        raise EvaluatorError(f"outputs do not match cases; missing={missing}, unexpected={unexpected}")
    results: list[dict[str, Any]] = []
    controls: dict[str, Any] = {}
    excluded = 0
    for case in cases:
        answerability = case.get("answerability") if isinstance(case, Mapping) else None
        is_unanswerable = isinstance(answerability, Mapping) and answerability.get("status") == "unanswerable"
        result = evaluate_case(case, outputs[_case_id(case)], retrieval_k=retrieval_k)
        results.append(result)
        if is_unanswerable or case.get("case_kind") == "abstention":
            excluded += 1
        if include_controls and str(case.get("family", "")).lower() == "retrieval" and not is_unanswerable:
            controls[_case_id(case)] = _control_case(case, k=retrieval_k, token_counts=None)
    if enforce_benchmark:
        _validate_benchmark_population(cases, results)
    events: list[SafetyEvent] = []
    gate_denominators: dict[str, int] = defaultdict(int)
    for result in results:
        for raw_event in result.get("safety_events", []):
            if not isinstance(raw_event, Mapping):
                raise EvaluatorError("safety event must be an object")
            events.append(SafetyEvent(
                gate=raw_event.get("gate"),
                case_id=raw_event.get("case_id"),
                detail_code=raw_event.get("detail_code"),
                review_required=bool(raw_event.get("review_required", False)),
            ))
        for gate, denominator in result.get("gate_denominators", {}).items():
            gate_denominators[gate] += _nonnegative_int(denominator, f"gate_denominators.{gate}")
    gate_rows = gate_summary(events, len(results) - excluded, attempt_denominators=gate_denominators)
    report = {
        "schema_version": REPORT_SCHEMA_VERSION,
        "report_type": "brain_eleven_ig01c_evaluation",
        "evaluator_version": EVALUATOR_VERSION,
        "corpus": {
            "corpus_version": corpus_version,
            "split": split,
            "case_count": len(case_ids),
            "scored_case_count": len(case_ids) - excluded,
            "excluded_case_count": excluded,
            "case_ids": sorted(case_ids),
        },
        "source": _safe_source({
            "git_sha": git_sha or None,
            "seed": seed,
            "retrieval_k": retrieval_k,
            "source_fingerprint": source_fingerprint or None,
        }),
        "metrics": _aggregate_metrics(results),
        "safety_gates": gate_rows,
        "cases": [
            {
                "case_id": result["case_id"],
                "family": result["family"],
                "metrics": result.get("metrics", {}),
                "violations": result.get("violations", []),
                "passed": bool(result.get("passed", False)),
            }
            for result in sorted(results, key=lambda item: item["case_id"])
        ],
        "controls": controls,
    }
    validate_report(report)
    return report


def _walk_report(value: Any, path: str = "report") -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            lowered = str(key).lower()
            if lowered in _BANNED_REPORT_KEYS or any(
                marker in lowered for marker in ("secret", "password", "credential", "api_key")
            ):
                raise EvaluatorError(f"{path}.{key} contains prohibited raw content")
            _walk_report(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _walk_report(child, f"{path}[{index}]")
    elif isinstance(value, float) and not math.isfinite(value):
        raise EvaluatorError(f"{path} contains a non-finite number")


def validate_report(report: Mapping[str, Any]) -> dict[str, Any]:
    """Validate report shape, finite metrics and the nine independent gates."""

    if not isinstance(report, Mapping):
        raise EvaluatorError("report must be an object")
    _walk_report(report)
    if report.get("schema_version") != REPORT_SCHEMA_VERSION:
        raise EvaluatorError("unsupported report schema version")
    if report.get("report_type") != "brain_eleven_ig01c_evaluation":
        raise EvaluatorError("invalid IG01-C report type")
    corpus = report.get("corpus")
    if not isinstance(corpus, Mapping):
        raise EvaluatorError("report.corpus must be an object")
    ids = corpus.get("case_ids")
    if not isinstance(ids, list) or ids != sorted(ids) or len(ids) != len(set(ids)) or not ids:
        raise EvaluatorError("report.corpus.case_ids must be sorted and unique")
    if corpus.get("case_count") != len(ids):
        raise EvaluatorError("report.corpus.case_count mismatch")
    if corpus.get("scored_case_count", -1) + corpus.get("excluded_case_count", -1) != len(ids):
        raise EvaluatorError("report corpus counts do not add up")
    gates = report.get("safety_gates")
    if not isinstance(gates, Mapping) or set(gates) != set(ALL_GATES):
        raise EvaluatorError("report.safety_gates must contain exactly the IG01-C gates")
    for gate in HARD_ZERO_GATES:
        row = gates[gate]
        if not isinstance(row, Mapping) or not isinstance(row.get("count"), int) or not isinstance(row.get("passed"), bool):
            raise EvaluatorError(f"invalid hard gate row: {gate}")
        if row["passed"] != (row["count"] == 0):
            raise EvaluatorError(f"hard gate pass state inconsistent: {gate}")
    for gate in ("false_supersession", "false_commitment"):
        row = gates[gate]
        if not isinstance(row, Mapping) or not isinstance(row.get("rate"), (int, float)):
            raise EvaluatorError(f"invalid near-zero gate row: {gate}")
        if not math.isfinite(float(row["rate"])) or not isinstance(row.get("passed"), bool):
            raise EvaluatorError(f"invalid near-zero gate value: {gate}")
        reviews = row.get("review_records", [])
        if not isinstance(reviews, list) or len(reviews) != row.get("count"):
            raise EvaluatorError(f"near-zero gate review records incomplete: {gate}")
    cases = report.get("cases")
    if not isinstance(cases, list) or [item.get("case_id") for item in cases] != ids:
        raise EvaluatorError("report.cases must match sorted case IDs")
    return dict(report)


def write_report(path: Path | str, report: Mapping[str, Any]) -> None:
    payload = validate_report(report)
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        descriptor, name = tempfile.mkstemp(dir=destination.parent, prefix=f".{destination.name}.", suffix=".tmp")
        temporary = Path(name)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, sort_keys=True, indent=2, ensure_ascii=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(destination)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def read_report(path: Path | str) -> dict[str, Any]:
    source = Path(path)
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise EvaluatorError(f"cannot read report {source}: {error}") from error
    return validate_report(payload)
