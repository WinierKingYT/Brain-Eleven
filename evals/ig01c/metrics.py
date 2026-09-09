"""Pure metric functions for the IG01-C evaluator.

The functions in this module accept primitive mappings and sequences only.  No
production retriever, extractor, lifecycle resolver or persistence class is
imported.  Every metric carries its numerator and denominator so a report
cannot hide an empty or inapplicable measurement.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
import math
from typing import Any

from .contracts import (
    HARD_ZERO_GATES,
    NEAR_ZERO_GATES,
    EvaluationContractError,
    MetricValue,
    SafetyEvent,
)


_NONE_COMMITMENTS = frozenset({"", "none", "no_commitment", "question", "hypothetical", "negation"})
_NON_USER_ROLES = frozenset({"assistant", "assistant_proposal", "quoted_external", "tool", "system"})
_VALID_REFERENCE_STATUSES = frozenset({"RESOLVED_TARGET", "AMBIGUOUS", "NO_TARGET", "REVIEW_REQUIRED"})
_VALID_LIFECYCLE_OPS = frozenset({"CONFIRM", "SUPERSEDE", "CORRECT", "RESOLVE", "REOPEN"})
_TRANSITIONS = {
    "CONFIRM": {"active": frozenset({"active"})},
    "SUPERSEDE": {"active": frozenset({"superseded"})},
    "CORRECT": {"active": frozenset({"superseded"})},
    "RESOLVE": {"active": frozenset({"resolved"})},
    "REOPEN": {"resolved": frozenset({"active"})},
}


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise EvaluationContractError(f"{field} must be a non-empty string")
    return value.strip()


def _norm(value: Any) -> str:
    return value.strip().lower() if isinstance(value, str) else ""


def _ids(values: Iterable[Any], field: str) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise EvaluationContractError(f"{field} must be a sequence of IDs")
    try:
        result = tuple(_text(value, f"{field} item") for value in values)
    except TypeError as error:
        raise EvaluationContractError(f"{field} must be a sequence of IDs") from error
    if len(result) != len(set(result)):
        raise EvaluationContractError(f"{field} must not contain duplicate IDs")
    return result


def _nonnegative_int(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise EvaluationContractError(f"{field} must be a non-negative integer")
    return value


def _ratio(
    numerator: int | float,
    denominator: int | float,
    *,
    not_applicable: bool = False,
    empty_selection: bool = False,
) -> MetricValue:
    if denominator < 0 or numerator < 0:
        raise EvaluationContractError("metric ratios require non-negative values")
    if not_applicable:
        return MetricValue(None, numerator, denominator, not_applicable=True)
    if denominator == 0:
        return MetricValue(0.0, numerator, denominator, empty_selection=empty_selection)
    return MetricValue(float(numerator) / float(denominator), numerator, denominator)


def precision_at_k(retrieved_ids: Sequence[str], relevant_ids: Iterable[str], k: int) -> MetricValue:
    """Return Precision@K using the declared K as the denominator.

    Underfilling the declared budget is therefore visible as lower precision;
    ``k=0`` is an explicit empty-selection result rather than a perfect score.
    """

    retrieved = _ids(retrieved_ids, "retrieved_ids")
    relevant = frozenset(_ids(relevant_ids, "relevant_ids"))
    k = _nonnegative_int(k, "k")
    top = retrieved[:k]
    return _ratio(len(set(top) & relevant), k, empty_selection=k == 0)


def recall_at_k(retrieved_ids: Sequence[str], relevant_ids: Iterable[str], k: int) -> MetricValue:
    retrieved = _ids(retrieved_ids, "retrieved_ids")
    relevant = frozenset(_ids(relevant_ids, "relevant_ids"))
    k = _nonnegative_int(k, "k")
    if not relevant:
        return _ratio(0, 0, not_applicable=True)
    top = retrieved[:k]
    return _ratio(len(set(top) & relevant), len(relevant))


def f1_score(precision: MetricValue, recall: MetricValue) -> MetricValue:
    """Compute F1 while preserving not-applicable semantics."""

    if precision.not_applicable or recall.not_applicable:
        return _ratio(0, 0, not_applicable=True)
    p = precision.value or 0.0
    r = recall.value or 0.0
    if p + r == 0:
        return _ratio(0, 1)
    return _ratio(2 * p * r / (p + r), 1)


def mean_reciprocal_rank(retrieved_ids: Sequence[str], relevant_ids: Iterable[str]) -> MetricValue:
    retrieved = _ids(retrieved_ids, "retrieved_ids")
    relevant = frozenset(_ids(relevant_ids, "relevant_ids"))
    if not relevant:
        return _ratio(0, 0, not_applicable=True)
    for rank, item_id in enumerate(retrieved, 1):
        if item_id in relevant:
            return _ratio(1.0 / rank, 1)
    return _ratio(0, 1)


def mandatory_recall(retrieved_ids: Sequence[str], mandatory_ids: Iterable[str]) -> MetricValue:
    retrieved = _ids(retrieved_ids, "retrieved_ids")
    mandatory = frozenset(_ids(mandatory_ids, "mandatory_ids"))
    if not mandatory:
        return _ratio(0, 0, not_applicable=True)
    return _ratio(len(set(retrieved) & mandatory), len(mandatory))


def noise_ratio(retrieved_ids: Sequence[str], relevant_ids: Iterable[str]) -> MetricValue:
    retrieved = _ids(retrieved_ids, "retrieved_ids")
    relevant = frozenset(_ids(relevant_ids, "relevant_ids"))
    noise = len([item_id for item_id in retrieved if item_id not in relevant])
    return _ratio(noise, len(retrieved), empty_selection=not retrieved)


def token_waste(
    retrieved_ids: Sequence[str],
    relevant_ids: Iterable[str],
    token_counts: Mapping[str, int],
) -> MetricValue:
    """Measure raw tokens spent on selected IDs outside the relevant set.

    The contract defines token waste as a sum, rather than a ratio.  The
    denominator is retained as the available token total for auditability;
    callers must use ``value``/``numerator`` as the raw wasted-token count.
    """

    retrieved = _ids(retrieved_ids, "retrieved_ids")
    relevant = frozenset(_ids(relevant_ids, "relevant_ids"))
    if not isinstance(token_counts, Mapping):
        raise EvaluationContractError("token_counts must be a mapping")
    total = 0
    wasted = 0
    for item_id in retrieved:
        if item_id not in token_counts:
            raise EvaluationContractError(f"token_counts is missing {item_id}")
        count = _nonnegative_int(token_counts[item_id], f"token_counts[{item_id}]")
        total += count
        if item_id not in relevant:
            wasted += count
    if not retrieved:
        return MetricValue(0.0, 0, 0, empty_selection=True)
    return MetricValue(float(wasted), wasted, total)


def _metric_map(**values: MetricValue) -> dict[str, dict[str, Any]]:
    return {name: value.as_dict() for name, value in sorted(values.items())}


def _event(gate: str, case_id: str, code: str, *, review: bool = False) -> SafetyEvent:
    return SafetyEvent(gate=gate, case_id=case_id, detail_code=code, review_required=review)


def _case_id(case: Mapping[str, Any]) -> str:
    if not isinstance(case, Mapping):
        raise EvaluationContractError("case must be an object")
    return _text(case.get("case_id"), "case.case_id")


def _case_ids(case: Mapping[str, Any], name: str) -> tuple[str, ...]:
    value = case.get(name, case.get(name.replace("_ids", ""), []))
    if value is None:
        return ()
    return _ids(value, f"case.{name}")


def _metadata_by_id(case: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    raw = case.get("candidate_metadata", case.get("memories", {}))
    if raw is None:
        return {}
    if isinstance(raw, Mapping):
        values = raw.items()
    elif isinstance(raw, Sequence) and not isinstance(raw, (str, bytes)):
        values = ((item.get("id", item.get("memory_id")), item) for item in raw if isinstance(item, Mapping))
    else:
        raise EvaluationContractError("candidate_metadata must be an object or array")
    normalized: dict[str, Mapping[str, Any]] = {}
    for key, value in values:
        item_id = _text(key, "candidate metadata ID")
        if not isinstance(value, Mapping):
            raise EvaluationContractError(f"candidate_metadata[{item_id}] must be an object")
        if item_id in normalized:
            raise EvaluationContractError(f"candidate metadata contains duplicate ID: {item_id}")
        normalized[item_id] = value
    return normalized


def evaluate_retrieval_case(
    case: Mapping[str, Any],
    retrieved_ids: Sequence[str],
    *,
    k: int = 5,
    token_counts: Mapping[str, int] | None = None,
) -> dict[str, Any]:
    """Evaluate one ranked retrieval output and immutable safety labels."""

    case_id = _case_id(case)
    retrieved = _ids(retrieved_ids, "retrieved_ids")
    required = _case_ids(case, "required_ids")
    acceptable = _case_ids(case, "acceptable_ids") or _case_ids(case, "useful_ids")
    forbidden = frozenset(_case_ids(case, "forbidden_ids"))
    mandatory = (_case_ids(case, "mandatory_ids") or required)
    mandatory = tuple(item_id for item_id in mandatory if item_id not in forbidden)
    relevant = (frozenset(required) | frozenset(acceptable)) - forbidden
    top = retrieved[:_nonnegative_int(k, "k")]
    metadata = _metadata_by_id(case)
    project_id = case.get("project_id", case.get("project"))
    declared_candidates = _case_ids(case, "candidate_ids")
    allowed_ids = frozenset(declared_candidates) if declared_candidates else frozenset(metadata)
    foreign = 0
    superseded = 0
    resolved = 0
    unknown = 0
    for item_id in top:
        if item_id not in allowed_ids:
            unknown += 1
            continue
        item = metadata.get(item_id)
        if item is None:
            continue
        item_project = item.get("project_id", item.get("project"))
        if project_id is not None and item_project is not None and item_project != project_id:
            foreign += 1
        status = _norm(item.get("status"))
        superseded += status == "superseded"
        resolved += status == "resolved"
    forbidden_count = len(frozenset(top) & forbidden)
    events: list[SafetyEvent] = []
    if unknown:
        events.append(_event("forbidden_leakage", case_id, "unknown_candidate_selected"))
    if foreign:
        events.append(_event("wrong_project_leakage", case_id, "foreign_candidate_selected"))
    if forbidden_count:
        events.append(_event("forbidden_leakage", case_id, "forbidden_candidate_selected"))
    if superseded:
        events.append(_event("superseded_leakage", case_id, "superseded_candidate_selected"))
    if resolved:
        events.append(_event("resolved_leakage", case_id, "resolved_candidate_selected"))
    token_metric: MetricValue
    if token_counts is not None:
        token_metric = token_waste(top, relevant, token_counts)
    else:
        available_counts = {
            item_id: metadata[item_id]["token_count"]
            for item_id in top
            if item_id in metadata and "token_count" in metadata[item_id]
        }
        if top and len(available_counts) == len(top):
            token_metric = token_waste(top, relevant, available_counts)
        else:
            token_metric = _ratio(0, 0, not_applicable=True)
    precision = precision_at_k(retrieved, relevant, k)
    recall = recall_at_k(retrieved, required, k)
    metrics = _metric_map(
        precision_at_k=precision,
        recall_at_k=recall,
        f1=f1_score(precision, recall),
        mrr=mean_reciprocal_rank(retrieved, relevant),
        mandatory_recall=mandatory_recall(top, mandatory),
        noise_ratio=noise_ratio(top, relevant),
        token_waste=token_metric,
        context_precision=_ratio(len(set(top) & relevant), len(top), empty_selection=not top),
    )
    return {
        "case_id": case_id,
        "family": "retrieval",
        "retrieved_ids": list(retrieved),
        "metrics": metrics,
        "safety_events": [item.as_dict() for item in events],
        "gate_denominators": {},
        "violations": sorted({item.gate for item in events}),
        "passed": not events,
    }


def _mapping(value: Any, field: str) -> Mapping[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise EvaluationContractError(f"{field} must be an object")
    return value


def _committed(value: Any) -> bool:
    return _norm(value) not in _NONE_COMMITMENTS


def _expected(case: Mapping[str, Any]) -> Mapping[str, Any]:
    expected = case.get("expected")
    if expected is None:
        expected = case.get("expected_result", {})
    return _mapping(expected, "case.expected")


def _field_equal(left: Any, right: Any) -> bool:
    if isinstance(left, str) or isinstance(right, str):
        return _norm(left) == _norm(right)
    return left == right


def _proposition_match(expected: Mapping[str, Any], predicted: Mapping[str, Any]) -> bool:
    """Match the complete typed proposition, including semantic identity."""

    fields = (
        "commitment", "memory_type", "state_operation", "correction",
        "target_behavior", "scope", "temporal_scope", "source_role",
        "claim_key", "subject", "predicate", "object", "value",
    )
    compared = [field for field in fields if field in expected]
    if not compared:
        return False
    aliases = {"object": ("object", "value"), "value": ("value", "object")}
    for field in compared:
        predicted_value = predicted.get(field)
        if predicted_value is None and field in aliases:
            predicted_value = next((predicted.get(alias) for alias in aliases[field] if alias in predicted), None)
        if not _field_equal(predicted_value, expected.get(field)):
            return False
    return True


def _confidence(value: Any, field: str = "confidence") -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise EvaluationContractError(f"{field} must be numeric")
    result = float(value)
    if not math.isfinite(result) or not 0 <= result <= 1:
        raise EvaluationContractError(f"{field} must be finite and in [0, 1]")
    return result


def _ece(confidence: float | None, correct: bool) -> MetricValue:
    if confidence is None:
        return _ratio(0, 0, not_applicable=True)
    # A one-item ECE has one deterministic bin; this is also the batch formula
    # when aggregate_ece receives these values and their sample counts.
    error = abs((1.0 if correct else 0.0) - confidence)
    return _ratio(error, 1)


def expected_calibration_error(samples: Sequence[tuple[float, bool]], bins: int = 10) -> MetricValue:
    """Return the frozen ten-bin expected calibration error."""

    if not samples:
        return _ratio(0, 0, not_applicable=True)
    if bins != 10:
        raise EvaluationContractError("IG01-C ECE is defined with exactly ten bins")
    buckets: list[list[tuple[float, bool]]] = [[] for _ in range(bins)]
    for confidence, correct in samples:
        value = _confidence(confidence)
        if value is None:
            raise EvaluationContractError("ECE samples require confidence")
        index = min(int(value * bins), bins - 1)
        buckets[index].append((value, bool(correct)))
    weighted_error = 0.0
    for bucket in buckets:
        if not bucket:
            continue
        accuracy = sum(1.0 if correct else 0.0 for _, correct in bucket) / len(bucket)
        mean_confidence = sum(confidence for confidence, _ in bucket) / len(bucket)
        weighted_error += abs(accuracy - mean_confidence) * len(bucket)
    return MetricValue(weighted_error / len(samples), weighted_error, len(samples))


def evaluate_extraction_case(case: Mapping[str, Any], predicted: Mapping[str, Any] | None) -> dict[str, Any]:
    """Evaluate typed proposition output without writing canonical truth."""

    case_id = _case_id(case)
    expected = _expected(case)
    prediction = _mapping(predicted, "predicted extraction")
    expected_commit = _committed(expected.get("commitment"))
    predicted_commit = _committed(prediction.get("commitment"))
    proposition_correct = expected_commit and predicted_commit and _proposition_match(expected, prediction)
    expected_memory_type = _norm(expected.get("memory_type"))
    predicted_memory_type = _norm(prediction.get("memory_type"))
    typed_prediction = bool(predicted_memory_type)
    wrong_type = typed_prediction and (
        not expected_memory_type or predicted_memory_type != expected_memory_type
    )
    expected_scope = _norm(expected.get("scope"))
    predicted_scope = _norm(prediction.get("scope"))
    wrong_scope = bool(predicted_scope) and bool(expected_scope) and predicted_scope != expected_scope
    false_commit = predicted_commit and not expected_commit
    expected_role = _norm(expected.get("source_role"))
    predicted_role = _norm(prediction.get("source_role"))
    assistant_as_user = predicted_commit and (
        expected_role in _NON_USER_ROLES
        or (predicted_role == "user" and expected_role in _NON_USER_ROLES)
    )
    canonical_commit = bool(prediction.get("canonical_commit", False))
    events: list[SafetyEvent] = []
    if assistant_as_user:
        events.append(_event("assistant_as_user_commitment", case_id, "non_user_proposition_committed"))
    if canonical_commit:
        events.append(_event("forbidden_leakage", case_id, "evaluator_output_requests_canonical_commit"))
    if false_commit:
        events.append(_event("false_commitment", case_id, "unexpected_commitment", review=True))
    confidence = _confidence(prediction.get("confidence"))
    metrics = _metric_map(
        decision_precision=_ratio(1 if proposition_correct else 0, 1 if predicted_commit else 0, not_applicable=not predicted_commit),
        decision_recall=_ratio(1 if proposition_correct else 0, 1 if expected_commit else 0, not_applicable=not expected_commit),
        false_commitment_rate=_ratio(1 if false_commit else 0, 1 if expected_commit else 0, not_applicable=not expected_commit),
        assistant_as_user_rate=_ratio(1 if assistant_as_user else 0, 1 if expected_role in _NON_USER_ROLES else 0, not_applicable=expected_role not in _NON_USER_ROLES),
        wrong_type_rate=_ratio(1 if wrong_type else 0, 1 if typed_prediction else 0, not_applicable=not typed_prediction),
        wrong_scope_rate=_ratio(1 if wrong_scope else 0, 1 if predicted_scope else 0, not_applicable=not predicted_scope),
        ece=_ece(confidence, proposition_correct),
    )
    return {
        "case_id": case_id,
        "family": "extraction",
        "metrics": metrics,
        "safety_events": [item.as_dict() for item in events],
        "gate_denominators": {"false_commitment": 1 if expected_commit else 0},
        "violations": sorted({item.gate for item in events}),
        "proposition_correct": proposition_correct,
        "ece_sample": None if confidence is None else {"confidence": confidence, "correct": bool(proposition_correct)},
        "passed": not events,
    }


def _reference_expected(case: Mapping[str, Any]) -> tuple[bool, str | None, str | None]:
    expected = _expected(case)
    primary = _mapping(_mapping(case.get("labels"), "case.labels").get("primary"), "case.labels.primary")
    status = expected.get("status", expected.get("target_status"))
    target = expected.get("target_id", expected.get("target"))
    abstain = bool(expected.get("abstain", primary.get("abstain", False)))
    if target is not None:
        target = _text(target, "expected target_id")
    return abstain or target is None, target, _norm(status) or None


def _reference_status(value: Any) -> str:
    status = _text(value, "reference status").upper().replace("-", "_").replace(" ", "_")
    if status in {"ABSTAIN", "NONE"}:
        status = "NO_TARGET"
    if status not in _VALID_REFERENCE_STATUSES:
        raise EvaluationContractError(f"invalid reference status: {status}")
    return status


def evaluate_reference_case(case: Mapping[str, Any], predicted: Mapping[str, Any] | None) -> dict[str, Any]:
    case_id = _case_id(case)
    expected_abstain, expected_target, expected_status = _reference_expected(case)
    prediction = _mapping(predicted, "predicted reference")
    status = _reference_status(prediction.get("status", "NO_TARGET"))
    target = prediction.get("target_id", prediction.get("target"))
    if target is not None:
        target = _text(target, "predicted target_id")
    candidates = prediction.get("candidate_targets", prediction.get("candidate_ids", [])) or []
    candidate_ids = _ids(candidates, "candidate_targets")
    operation = _norm(prediction.get("operation", prediction.get("lifecycle_operation"))).upper()
    correct_abstain = expected_abstain and status in {"AMBIGUOUS", "NO_TARGET", "REVIEW_REQUIRED"} and target is None
    correct_target = bool(expected_target) and status == "RESOLVED_TARGET" and target == expected_target
    target_attempt = bool(target) or status == "RESOLVED_TARGET"
    target_project = prediction.get("target_project_id", prediction.get("project_id", case.get("project_id")))
    cross_project = bool(target_attempt and case.get("project_id") is not None and target_project is not None and target_project != case.get("project_id"))
    ambiguous_guess = expected_abstain and status == "RESOLVED_TARGET"
    false_correction = operation == "CORRECT" and not (correct_target or expected_status in {"correct", "resolve"})
    false_supersession = operation == "SUPERSEDE" and not correct_target
    events: list[SafetyEvent] = []
    if cross_project:
        events.append(_event("cross_project_target", case_id, "target_project_mismatch"))
    if ambiguous_guess:
        events.append(_event("false_supersession", case_id, "ambiguous_reference_guessed", review=True))
    if false_supersession:
        events.append(_event("false_supersession", case_id, "supersession_target_mismatch", review=True))
    if false_correction:
        events.append(_event("false_commitment", case_id, "correction_target_mismatch", review=True))
    metrics = _metric_map(
        correct_target_rate=_ratio(1 if correct_target else 0, 1 if expected_target else 0, not_applicable=not bool(expected_target)),
        ambiguous_abstention_rate=_ratio(1 if correct_abstain else 0, 1 if expected_abstain else 0, not_applicable=not expected_abstain),
        wrong_project_target_rate=_ratio(1 if cross_project else 0, 1 if target_attempt else 0, not_applicable=not target_attempt),
        false_correction_rate=_ratio(1 if false_correction else 0, 1 if operation == "CORRECT" else 0, not_applicable=operation != "CORRECT"),
    )
    return {
        "case_id": case_id,
        "family": "reference_resolution",
        "metrics": metrics,
        "candidate_targets": list(candidate_ids),
        "safety_events": [item.as_dict() for item in events],
        "gate_denominators": {
            "false_supersession": 1 if operation == "SUPERSEDE" else 0,
            "false_commitment": 1 if operation == "CORRECT" else 0,
        },
        "violations": sorted({item.gate for item in events}),
        "passed": not events,
    }


def evaluate_lifecycle_case(case: Mapping[str, Any], result: Mapping[str, Any] | None) -> dict[str, Any]:
    case_id = _case_id(case)
    expected = _expected(case)
    value = _mapping(result, "lifecycle result")
    operation = _text(value.get("operation", value.get("lifecycle_operation", "")), "lifecycle operation").upper()
    if operation not in _VALID_LIFECYCLE_OPS:
        raise EvaluationContractError(f"invalid lifecycle operation: {operation}")
    from_status = _norm(value.get("from_status", expected.get("from_status", "active")))
    to_status = _norm(value.get("to_status", expected.get("to_status", "")))
    valid_transition = to_status in _TRANSITIONS[operation].get(from_status, frozenset())
    expected_operation = _norm(expected.get("operation", expected.get("lifecycle_operation"))).upper()
    expected_target = expected.get("target_id")
    target = value.get("target_id")
    target_match = expected_target is None or target == expected_target
    target_required = operation in {"SUPERSEDE", "CORRECT", "RESOLVE"}
    cycle = bool(value.get("cycle", False))
    history = value.get("history", []) or []
    if history:
        history = tuple(_norm(item) for item in history)
        cycle = cycle or len(history) != len(set(history))
    false_supersession = operation == "SUPERSEDE" and (
        expected_operation not in {"", "SUPERSEDE"} or not target_match or not target
    )
    if target_required and not target:
        valid_transition = False
    events: list[SafetyEvent] = []
    if cycle:
        events.append(_event("lifecycle_cycle", case_id, "repeated_lifecycle_state"))
    if false_supersession:
        events.append(_event("false_supersession", case_id, "unexpected_supersede", review=True))
    metrics = _metric_map(
        lifecycle_transition_safety=_ratio(1 if valid_transition and not cycle else 0, 1),
        false_supersession_rate=_ratio(1 if false_supersession else 0, 1 if operation == "SUPERSEDE" else 0, not_applicable=operation != "SUPERSEDE"),
    )
    return {
        "case_id": case_id,
        "family": "lifecycle",
        "metrics": metrics,
        "safety_events": [item.as_dict() for item in events],
        "gate_denominators": {"false_supersession": 1 if operation == "SUPERSEDE" else 0},
        "violations": sorted({item.gate for item in events}),
        "passed": not events and valid_transition,
    }


def evaluate_capture_case(case: Mapping[str, Any], result: Mapping[str, Any] | None) -> dict[str, Any]:
    """Evaluate capture/queue counters without observing a live worker."""

    case_id = _case_id(case)
    value = _mapping(result, "capture result")
    emitted = _nonnegative_int(value.get("emitted_events", 0), "emitted_events")
    lost = _nonnegative_int(value.get("lost_events", 0), "lost_events")
    replayed = _nonnegative_int(value.get("replayed_events", 0), "replayed_events")
    idempotent = _nonnegative_int(value.get("idempotent_correct_replays", 0), "idempotent_correct_replays")
    duplicate = _nonnegative_int(value.get("duplicate_effects", 0), "duplicate_effects")
    completed = _nonnegative_int(value.get("completed_jobs", 0), "completed_jobs")
    verified = _nonnegative_int(value.get("completed_jobs_with_verified_effect", 0), "completed_jobs_with_verified_effect")
    if lost > emitted:
        raise EvaluationContractError("lost_events cannot exceed emitted_events")
    if replayed > emitted:
        raise EvaluationContractError("replayed_events cannot exceed emitted_events")
    if idempotent > replayed:
        raise EvaluationContractError("idempotent_correct_replays cannot exceed replayed_events")
    if duplicate > replayed:
        raise EvaluationContractError("duplicate_effects cannot exceed replayed_events")
    if verified > completed:
        raise EvaluationContractError("verified effects cannot exceed completed_jobs")
    if completed > emitted:
        raise EvaluationContractError("completed_jobs cannot exceed emitted_events")
    events: list[SafetyEvent] = []
    if duplicate:
        events.append(_event("forbidden_leakage", case_id, "duplicate_canonical_effect"))
    metrics = _metric_map(
        capture_loss_rate=_ratio(lost, emitted, not_applicable=emitted == 0),
        duplicate_canonical_effect_rate=_ratio(duplicate, replayed, not_applicable=replayed == 0),
        replay_correctness=_ratio(idempotent, replayed, not_applicable=replayed == 0),
        terminal_effect_agreement=_ratio(verified, completed, not_applicable=completed == 0),
    )
    return {
        "case_id": case_id,
        "family": "capture",
        "metrics": metrics,
        "safety_events": [item.as_dict() for item in events],
        "violations": sorted({item.gate for item in events}),
        "passed": not events,
    }


def evaluate_context_case(case: Mapping[str, Any], selected_ids: Sequence[str], *, token_counts: Mapping[str, int] | None = None) -> dict[str, Any]:
    """Evaluate minimum-context behavior using the same retrieval labels."""

    result = evaluate_retrieval_case(case, selected_ids, k=len(selected_ids), token_counts=token_counts)
    result["family"] = "context_compilation"
    selected = _ids(selected_ids, "selected_ids")
    required = _case_ids(case, "required_ids")
    acceptable = _case_ids(case, "acceptable_ids")
    relevant = frozenset(required) | frozenset(acceptable)
    duplicates = len(selected) - len(set(selected))
    result["metrics"]["redundancy_rate"] = _ratio(duplicates, len(selected), empty_selection=not selected).as_dict()
    result["metrics"]["mandatory_context_coverage"] = mandatory_recall(selected, required).as_dict()
    if relevant:
        result["metrics"]["irrelevant_context_rate"] = noise_ratio(selected, relevant).as_dict()
    return result


def aggregate_metric_values(values: Sequence[MetricValue], *, pooled: bool = False) -> MetricValue:
    """Aggregate metrics with explicit counts.

    Case-scored metrics are unweighted macro means. Event/job metrics use the
    pooled numerator and denominator required by IG01-A.
    """

    applicable = [item for item in values if not item.not_applicable]
    if not applicable:
        return _ratio(0, 0, not_applicable=True)
    if pooled:
        numerator = sum(item.numerator for item in applicable)
        denominator = sum(item.denominator for item in applicable)
        if denominator == 0:
            return _ratio(0, 0, not_applicable=True)
        return _ratio(numerator, denominator)
    total = sum(item.value or 0.0 for item in applicable)
    return MetricValue(total / len(applicable), total, len(applicable))


def gate_summary(
    events: Sequence[SafetyEvent],
    case_count: int,
    *,
    attempt_denominators: Mapping[str, int] | None = None,
) -> dict[str, dict[str, Any]]:
    """Produce independent hard-gate rows; averages cannot mask violations."""

    if case_count < 0:
        raise EvaluationContractError("case_count must be non-negative")
    summary: dict[str, dict[str, Any]] = {}
    denominators = dict(attempt_denominators or {})
    for gate, value in denominators.items():
        if gate not in NEAR_ZERO_GATES or not isinstance(value, int) or value < 0:
            raise EvaluationContractError(f"invalid near-zero denominator: {gate}")
    for gate in HARD_ZERO_GATES:
        hits = [event for event in events if event.gate == gate]
        summary[gate] = {
            "count": len(hits),
            "denominator": case_count,
            "passed": not hits,
            "event_case_ids": sorted({event.case_id for event in hits}),
            "review_records": [event.as_dict() for event in hits if event.review_required],
        }
    for gate, threshold in NEAR_ZERO_GATES.items():
        hits = [event for event in events if event.gate == gate]
        denominator = denominators.get(gate, 0)
        if denominator == 0 and hits:
            # A positive near-zero event without a positive attempt denominator
            # is itself unsafe; use one event as a deterministic fail-closed
            # denominator rather than silently reporting not-applicable.
            denominator = len(hits)
        rate = len(hits) / denominator if denominator else 0.0
        reviews = [event.as_dict() for event in hits if event.review_required]
        summary[gate] = {
            "count": len(hits),
            "denominator": denominator,
            "rate": rate,
            "threshold": threshold,
            "passed": rate <= threshold and len(reviews) == len(hits),
            "event_case_ids": sorted({event.case_id for event in hits}),
            "review_records": reviews,
        }
    return summary
