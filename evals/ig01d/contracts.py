"""Strict contracts for IG01-D revision-bound baseline evidence."""

from __future__ import annotations

import math
import re
from collections.abc import Mapping, Sequence
from typing import Any


IG01D_SCHEMA_VERSION = 1
EVALUATOR_VERSION = "ig01c-1.0.0"
REPORT_TYPE = "brain_eleven_ig01d_baseline"
PAIR_REPORT_TYPE = "brain_eleven_ig01d_pair"
PROVIDER_KEYS = ("v1", "v2")
_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_FINGERPRINT_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:/-]{0,127}$")

_BASELINE_KEYS = frozenset(
    {"schema_version", "report_type", "evaluator_version", "provider", "corpus", "source", "metrics", "invariants", "measurement", "cases"}
)
_PROVIDER_KEYS = frozenset({"id", "role", "capabilities"})
_CAPABILITY_KEYS = frozenset({"selection", "production_mutation"})
_CORPUS_KEYS = frozenset({"corpus_version", "fixture_id", "suite", "split", "task_count", "task_ids", "split_fingerprint"})
_SOURCE_KEYS = frozenset({"git_sha", "corpus_version", "evaluator_version", "evaluation_source_fingerprint", "seed", "noise_count"})
_METRIC_KEYS = frozenset(
    {
        "case_count", "context_precision", "context_recall", "selected_items", "relevant_selected_items",
        "required_items", "required_selected_items", "wrong_project_leakage_rate", "forbidden_context_rate",
        "superseded_leakage_rate", "resolved_leakage_rate", "unlabeled_context_rate",
    }
)
_INVARIANT_NAMES = frozenset({"forbidden_context", "resolved_lifecycle_leakage", "superseded_lifecycle_leakage", "wrong_project_leakage"})
_INVARIANT_KEYS = frozenset({"state", "failed_case_ids", "unsupported_case_ids", "not_applicable_case_ids"})
_MEASUREMENT_KEYS = frozenset({"elapsed_ms", "case_count", "per_case_mean_ms", "p50_ms", "p95_ms", "budget_measurement"})
_CASE_KEYS = frozenset(
    {"task_id", "project_id", "expected", "selected_ids", "missing_required_ids", "unexpected_selected_ids", "forbidden_selected_ids", "metrics", "invariants", "violations", "passed"}
)
_EXPECTED_KEYS = frozenset({"required", "useful", "forbidden"})
_CASE_METRIC_KEYS = frozenset(
    {
        "task_id", "selected_count", "relevant_selected_count", "required_count", "required_selected_count", "useful_selected_count",
        "context_precision", "context_recall", "wrong_project_selected_count", "wrong_project_leakage_count",
        "forbidden_context_count", "superseded_selected_count", "superseded_leakage_count", "resolved_selected_count",
        "resolved_leakage_count", "unlabeled_selection_count",
    }
)
_COMPARISON_KEYS = frozenset({"schema_version", "comparison_type", "baseline", "candidate", "corpus", "metric_deltas", "invariant_changes", "candidate_gate", "outcome"})
_COMPARISON_CORPUS_KEYS = frozenset({"fixture_id", "suite", "task_count"})
_METRIC_DELTA_KEYS = frozenset({"baseline", "candidate", "delta"})
_GATE_KEYS = frozenset({"passed", "failed_invariants", "unsupported_invariants"})
_FEASIBILITY_KEYS = frozenset({"status", "provider_id", "reason", "case_count", "split", "holdout_included", "corpus_split_fingerprint", "precision", "empirical_ceiling", "elapsed_ms", "measurement"})
_TARGET_KEYS = frozenset({"formula", "margin", "realistic_gain", "program_floor", "targets", "quality_visibility"})
_TARGET_METRIC_KEYS = frozenset({"value", "status", "baseline"})
_QUALITY_VISIBILITY_KEYS = frozenset({"v2_must_exceed_v1", "promotion_allowed", "spike_status"})

# Reports may retain identifiers and numeric metrics, but never benchmark
# prompts, memory text, transcripts, or credentials.
_BANNED_KEYS = frozenset(
    {
        "prompt", "query", "text", "content", "transcript", "message",
        "raw", "raw_prompt", "raw_text", "raw_transcript", "memory_content",
        "secret", "secrets", "token", "tokens", "token_count", "password",
        "credential", "credentials", "api_key", "api_secret",
    }
)


class BaselineContractError(ValueError):
    """Raised when baseline evidence is malformed or unsafe to persist."""


def _mapping(value: Any, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise BaselineContractError(f"{field} must be an object")
    return value


def _closed_mapping(value: Any, field: str, allowed: frozenset[str]) -> Mapping[str, Any]:
    """Require a schema object to contain no undeclared fields."""

    mapping = _mapping(value, field)
    unknown = sorted(set(mapping) - allowed)
    if unknown:
        raise BaselineContractError(f"{field} contains unknown fields: {', '.join(unknown)}")
    return mapping


def _nonempty(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise BaselineContractError(f"{field} must be a non-empty string")
    return value.strip()


def _id(value: Any, field: str) -> str:
    value = _nonempty(value, field)
    if not _ID_RE.fullmatch(value):
        raise BaselineContractError(f"{field} is not a safe identifier")
    return value


def _sha(value: Any, field: str) -> str:
    value = _nonempty(value, field).lower()
    if not _SHA_RE.fullmatch(value):
        raise BaselineContractError(f"{field} must be a 40-character git SHA")
    return value


def _fingerprint(value: Any, field: str) -> str:
    value = _nonempty(value, field).lower()
    if not _FINGERPRINT_RE.fullmatch(value):
        raise BaselineContractError(f"{field} must be a sha256 fingerprint")
    return value


def _number(value: Any, field: str, *, nullable: bool = False) -> float | None:
    if value is None and nullable:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise BaselineContractError(f"{field} must be numeric")
    value = float(value)
    if not math.isfinite(value):
        raise BaselineContractError(f"{field} must be finite")
    return value


def _safe_tree(value: Any, path: str = "report") -> None:
    """Reject raw content recursively, including nested provider payloads."""

    if isinstance(value, Mapping):
        for key, child in value.items():
            if not isinstance(key, str) or not key.strip():
                raise BaselineContractError(f"{path} has an invalid key")
            lowered = key.strip().lower()
            if lowered in _BANNED_KEYS or any(
                marker in lowered for marker in ("prompt", "transcript", "secret", "password", "credential")
            ):
                raise BaselineContractError(f"{path}.{key} is not content-free")
            _safe_tree(child, f"{path}.{key}")
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for index, child in enumerate(value):
            _safe_tree(child, f"{path}[{index}]")


def _task_ids(value: Any, field: str) -> list[str]:
    if not isinstance(value, list) or not value:
        raise BaselineContractError(f"{field} must be a non-empty array")
    result = [_id(item, f"{field}[{index}]") for index, item in enumerate(value)]
    if result != sorted(result) or len(result) != len(set(result)):
        raise BaselineContractError(f"{field} must be unique and sorted")
    return result


def _validate_metrics(metrics: Any, field: str, *, case_count: int | None = None) -> Mapping[str, Any]:
    metrics = _closed_mapping(metrics, field, _METRIC_KEYS)
    if not isinstance(metrics.get("case_count"), int) or isinstance(metrics.get("case_count"), bool) or metrics.get("case_count", 0) <= 0:
        raise BaselineContractError(f"{field}.case_count must be positive")
    if case_count is not None and metrics["case_count"] != case_count:
        raise BaselineContractError(f"{field}.case_count does not match corpus task_count")
    for name in (
        "context_precision", "context_recall", "selected_items", "relevant_selected_items",
        "required_items", "required_selected_items", "wrong_project_leakage_rate",
        "forbidden_context_rate", "superseded_leakage_rate", "resolved_leakage_rate",
        "unlabeled_context_rate",
    ):
        if name in metrics:
            _number(metrics[name], f"{field}.{name}", nullable=True)
    return metrics


def _validate_invariants(invariants: Any, field: str) -> None:
    invariants = _closed_mapping(invariants, field, _INVARIANT_NAMES)
    for name, value in invariants.items():
        item = _closed_mapping(value, f"{field}.{name}", _INVARIANT_KEYS)
        if item.get("state") not in {"pass", "fail", "unsupported", "not_applicable"}:
            raise BaselineContractError(f"{field}.{name}.state is invalid")
        for key in ("failed_case_ids", "unsupported_case_ids", "not_applicable_case_ids"):
            ids = item.get(key)
            if not isinstance(ids, list) or any(not isinstance(case_id, str) for case_id in ids):
                raise BaselineContractError(f"{field}.{name}.{key} must be an array of identifiers")


def _validate_case_invariants(invariants: Any, field: str) -> None:
    """Case rows retain compact invariant states rather than full evidence."""

    invariants = _closed_mapping(invariants, field, _INVARIANT_NAMES)
    for name, state in invariants.items():
        if state not in {"pass", "fail", "unsupported", "not_applicable"}:
            raise BaselineContractError(f"{field}.{name} is an invalid invariant state")


def _validate_string_id_list(value: Any, field: str) -> None:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise BaselineContractError(f"{field} must be an array of identifiers")
    for index, item in enumerate(value):
        _id(item, f"{field}[{index}]")


def _validate_case(case: Any, field: str, *, expected_task_id: str) -> None:
    case = _closed_mapping(case, field, _CASE_KEYS)
    if case.get("task_id") != expected_task_id:
        raise BaselineContractError(f"{field}.task_id does not match corpus task_ids")
    if case.get("project_id") is not None:
        _id(case.get("project_id"), f"{field}.project_id")
    expected = _closed_mapping(case.get("expected"), f"{field}.expected", _EXPECTED_KEYS)
    for key in _EXPECTED_KEYS:
        _validate_string_id_list(expected.get(key), f"{field}.expected.{key}")
    for key in ("selected_ids", "missing_required_ids", "unexpected_selected_ids", "forbidden_selected_ids"):
        _validate_string_id_list(case.get(key), f"{field}.{key}")
    metrics = _closed_mapping(case.get("metrics"), f"{field}.metrics", _CASE_METRIC_KEYS)
    for key, value in metrics.items():
        if key == "task_id":
            if value != expected_task_id:
                raise BaselineContractError(f"{field}.metrics.task_id does not match task_id")
        elif isinstance(value, bool) or not isinstance(value, (int, float)):
            raise BaselineContractError(f"{field}.metrics.{key} must be numeric")
    _validate_case_invariants(case.get("invariants"), f"{field}.invariants")
    violations = case.get("violations")
    if not isinstance(violations, list) or any(not isinstance(item, str) for item in violations):
        raise BaselineContractError(f"{field}.violations must be an array")
    if not isinstance(case.get("passed"), bool):
        raise BaselineContractError(f"{field}.passed must be boolean")


def validate_baseline_report(report: Mapping[str, Any]) -> dict[str, Any]:
    """Validate one provider report without accepting raw benchmark content."""

    _safe_tree(report)
    report = _closed_mapping(report, "report", _BASELINE_KEYS)
    if report.get("schema_version") != IG01D_SCHEMA_VERSION:
        raise BaselineContractError("unsupported IG01-D report schema")
    if report.get("report_type") != REPORT_TYPE:
        raise BaselineContractError("unsupported IG01-D report type")
    if report.get("evaluator_version") != EVALUATOR_VERSION:
        raise BaselineContractError("report.evaluator_version does not match the frozen evaluator")
    provider = _closed_mapping(report.get("provider"), "report.provider", _PROVIDER_KEYS)
    provider_id = _id(provider.get("id"), "report.provider.id")
    if provider_id not in {"context_compiler_baseline_v1", "context_compiler_v2"}:
        raise BaselineContractError("report.provider.id is not an IG01-D provider")
    role = _nonempty(provider.get("role"), "report.provider.role")
    if role not in {"v1", "v2"}:
        raise BaselineContractError("report.provider.role is not an IG01-D role")
    expected_role = "v1" if provider_id == "context_compiler_baseline_v1" else "v2"
    if role != expected_role:
        raise BaselineContractError("report.provider.role does not match provider id")
    capabilities = _closed_mapping(provider.get("capabilities"), "report.provider.capabilities", _CAPABILITY_KEYS)
    if capabilities.get("selection") != "existing_provider_adapter" or capabilities.get("production_mutation") is not False:
        raise BaselineContractError("report.provider capabilities are not read-only")
    corpus = _closed_mapping(report.get("corpus"), "report.corpus", _CORPUS_KEYS)
    corpus_version = _nonempty(corpus.get("corpus_version"), "report.corpus.corpus_version")
    _id(corpus.get("fixture_id"), "report.corpus.fixture_id")
    if corpus.get("suite") != "public":
        raise BaselineContractError("IG01-D reports must use the public suite")
    if corpus.get("split") != ["dev", "test"]:
        raise BaselineContractError("IG01-D reports must use exactly DEV+TEST")
    task_ids = _task_ids(corpus.get("task_ids"), "report.corpus.task_ids")
    if not isinstance(corpus.get("task_count"), int) or isinstance(corpus.get("task_count"), bool) or corpus.get("task_count") != len(task_ids):
        raise BaselineContractError("report.corpus.task_count does not match task_ids")
    _fingerprint(corpus.get("split_fingerprint"), "report.corpus.split_fingerprint")
    source = _closed_mapping(report.get("source"), "report.source", _SOURCE_KEYS)
    _sha(source.get("git_sha"), "report.source.git_sha")
    source_corpus_version = _nonempty(source.get("corpus_version"), "report.source.corpus_version")
    source_evaluator_version = _nonempty(source.get("evaluator_version"), "report.source.evaluator_version")
    _fingerprint(source.get("evaluation_source_fingerprint"), "report.source.evaluation_source_fingerprint")
    if source_corpus_version != corpus_version or source_evaluator_version != EVALUATOR_VERSION:
        raise BaselineContractError("report source identity does not match the report contract")
    if source.get("seed") != 17 or source.get("noise_count") != 24:
        raise BaselineContractError("report source must use the frozen IG01-D seed/noise configuration")
    _validate_metrics(report.get("metrics"), "report.metrics", case_count=len(task_ids))
    _validate_invariants(report.get("invariants"), "report.invariants")
    measurement = _closed_mapping(report.get("measurement"), "report.measurement", _MEASUREMENT_KEYS)
    _number(measurement.get("elapsed_ms"), "report.measurement.elapsed_ms")
    if measurement.get("case_count") != len(task_ids):
        raise BaselineContractError("measurement.case_count does not match task_ids")
    cases = report.get("cases")
    if not isinstance(cases, list) or len(cases) != len(task_ids):
        raise BaselineContractError("report.cases must contain one row per task")
    case_ids = [case.get("task_id") if isinstance(case, Mapping) else None for case in cases]
    if case_ids != task_ids:
        raise BaselineContractError("report.cases must be ordered by task_id")
    for index, (case, task_id) in enumerate(zip(cases, task_ids)):
        _validate_case(case, f"report.cases[{index}]", expected_task_id=task_id)
    return dict(report)


def validate_pair_report(report: Mapping[str, Any]) -> dict[str, Any]:
    """Validate paired V1/V2 evidence and all same-input guarantees."""

    _safe_tree(report)
    report = _closed_mapping(report, "pair report", frozenset({"schema_version", "report_type", "evaluator_version", "corpus", "source", "providers", "comparison", "measurement", "feasibility", "target_derivation"}))
    if report.get("schema_version") != IG01D_SCHEMA_VERSION:
        raise BaselineContractError("unsupported IG01-D pair schema")
    if report.get("report_type") != PAIR_REPORT_TYPE:
        raise BaselineContractError("unsupported IG01-D pair report type")
    if report.get("evaluator_version") != EVALUATOR_VERSION:
        raise BaselineContractError("pair report.evaluator_version does not match the frozen evaluator")
    source = _closed_mapping(report.get("source"), "pair report.source", _SOURCE_KEYS)
    _sha(source.get("git_sha"), "pair report.source.git_sha")
    _fingerprint(source.get("evaluation_source_fingerprint"), "pair report.source.evaluation_source_fingerprint")
    source_corpus_version = _nonempty(source.get("corpus_version"), "pair report.source.corpus_version")
    source_evaluator_version = _nonempty(source.get("evaluator_version"), "pair report.source.evaluator_version")
    if source_evaluator_version != EVALUATOR_VERSION:
        raise BaselineContractError("pair report source evaluator does not match the frozen evaluator")
    if source.get("seed") != 17 or source.get("noise_count") != 24:
        raise BaselineContractError("pair report uses an unfrozen seed/noise configuration")
    corpus = _closed_mapping(report.get("corpus"), "pair report.corpus", _CORPUS_KEYS)
    corpus_version = _nonempty(corpus.get("corpus_version"), "pair report.corpus.corpus_version")
    if corpus_version != source_corpus_version:
        raise BaselineContractError("pair report corpus/source corpus_version differs")
    fixture_id = _id(corpus.get("fixture_id"), "pair report.corpus.fixture_id")
    if corpus.get("suite") != "public" or corpus.get("split") != ["dev", "test"]:
        raise BaselineContractError("pair report must be public DEV+TEST only")
    task_ids = _task_ids(corpus.get("task_ids"), "pair report.corpus.task_ids")
    if not isinstance(corpus.get("task_count"), int) or isinstance(corpus.get("task_count"), bool) or corpus.get("task_count") != len(task_ids):
        raise BaselineContractError("pair report.corpus.task_count does not match task_ids")
    split_fingerprint = _fingerprint(corpus.get("split_fingerprint"), "pair report.corpus.split_fingerprint")
    providers = _mapping(report.get("providers"), "pair report.providers")
    if set(providers) != set(PROVIDER_KEYS):
        raise BaselineContractError("pair report must contain v1 and v2")
    v1 = validate_baseline_report(providers["v1"])
    v2 = validate_baseline_report(providers["v2"])
    for label, provider in (("v1", v1), ("v2", v2)):
        provider_corpus = provider["corpus"]
        for key, expected in (
            ("corpus_version", corpus_version), ("fixture_id", fixture_id), ("suite", "public"),
            ("split", ["dev", "test"]), ("task_count", len(task_ids)), ("task_ids", task_ids),
            ("split_fingerprint", split_fingerprint),
        ):
            if provider_corpus.get(key) != expected:
                raise BaselineContractError(f"{label} corpus.{key} differs from pair corpus")
        provider_source = provider["source"]
        for key in ("git_sha", "corpus_version", "evaluator_version", "evaluation_source_fingerprint", "seed", "noise_count"):
            if provider_source.get(key) != source.get(key):
                raise BaselineContractError(f"{label} source.{key} differs from pair source")
        if provider["provider"]["role"] != label:
            raise BaselineContractError(f"{label} provider role does not match pair key")
    comparison = _closed_mapping(report.get("comparison"), "pair report.comparison", _COMPARISON_KEYS)
    if comparison.get("schema_version") != 1 or comparison.get("comparison_type") != "brain_eleven_evaluation_regression":
        raise BaselineContractError("comparison metadata does not match the frozen evaluator")
    if comparison.get("baseline") != {"provider_id": v1["provider"]["id"]}:
        raise BaselineContractError("comparison baseline does not identify V1")
    if comparison.get("candidate") != {"provider_id": v2["provider"]["id"]}:
        raise BaselineContractError("comparison candidate does not identify V2")
    comparison_corpus = _closed_mapping(comparison.get("corpus"), "pair report.comparison.corpus", _COMPARISON_CORPUS_KEYS)
    if comparison_corpus != {"fixture_id": fixture_id, "suite": "public", "task_count": len(task_ids)}:
        raise BaselineContractError("comparison corpus identity differs from pair corpus")
    metric_deltas = _closed_mapping(comparison.get("metric_deltas"), "pair report.comparison.metric_deltas", frozenset({"context_precision", "context_recall"}))
    for name, delta in metric_deltas.items():
        delta = _closed_mapping(delta, f"pair report.comparison.metric_deltas.{name}", _METRIC_DELTA_KEYS)
        for key in _METRIC_DELTA_KEYS:
            _number(delta.get(key), f"pair report.comparison.metric_deltas.{name}.{key}")
    invariant_changes = _closed_mapping(comparison.get("invariant_changes"), "pair report.comparison.invariant_changes", _INVARIANT_NAMES)
    for name, change in invariant_changes.items():
        change = _closed_mapping(change, f"pair report.comparison.invariant_changes.{name}", frozenset({"new_failed_case_ids", "resolved_failed_case_ids", "new_unsupported_case_ids", "resolved_unsupported_case_ids"}))
        for key in change:
            _validate_string_id_list(change[key], f"pair report.comparison.invariant_changes.{name}.{key}")
    gate = _closed_mapping(comparison.get("candidate_gate"), "pair report.comparison.candidate_gate", _GATE_KEYS)
    if not isinstance(gate.get("passed"), bool):
        raise BaselineContractError("comparison candidate_gate.passed must be boolean")
    _closed_mapping(gate.get("failed_invariants"), "pair report.comparison.candidate_gate.failed_invariants", _INVARIANT_NAMES)
    _closed_mapping(gate.get("unsupported_invariants"), "pair report.comparison.candidate_gate.unsupported_invariants", _INVARIANT_NAMES)
    if comparison.get("outcome") not in {"improved", "degraded", "unchanged", "inconclusive"}:
        raise BaselineContractError("comparison outcome is invalid")
    measurement = _closed_mapping(report.get("measurement"), "pair report.measurement", frozenset({"v1_elapsed_ms", "v2_elapsed_ms", "budget_measurement"}))
    for name in ("v1_elapsed_ms", "v2_elapsed_ms"):
        _number(measurement.get(name), f"pair report.measurement.{name}")
    feasibility = _closed_mapping(report.get("feasibility"), "pair report.feasibility", _FEASIBILITY_KEYS)
    status = _nonempty(feasibility.get("status"), "pair report.feasibility.status")
    if status not in {"SEMANTIC_UNAVAILABLE", "MEASURED"}:
        raise BaselineContractError("pair report.feasibility.status is invalid")
    if feasibility.get("provider_id") not in {"none", "openai_only", "sentence_transformers"}:
        raise BaselineContractError("pair report.feasibility.provider_id is invalid")
    _nonempty(feasibility.get("reason"), "pair report.feasibility.reason")
    if feasibility.get("case_count") != 50 or feasibility.get("split") != "dev":
        raise BaselineContractError("feasibility probe must cover exactly 50 DEV cases")
    _fingerprint(feasibility.get("corpus_split_fingerprint"), "pair report.feasibility.corpus_split_fingerprint")
    if feasibility.get("corpus_split_fingerprint") != split_fingerprint:
        raise BaselineContractError("feasibility corpus fingerprint differs from pair corpus")
    if feasibility.get("holdout_included") is not False:
        raise BaselineContractError("feasibility probe must explicitly exclude HOLDOUT")
    _number(feasibility.get("precision"), "pair report.feasibility.precision", nullable=True)
    _number(feasibility.get("empirical_ceiling"), "pair report.feasibility.empirical_ceiling", nullable=True)
    _number(feasibility.get("elapsed_ms"), "pair report.feasibility.elapsed_ms")
    _nonempty(feasibility.get("measurement"), "pair report.feasibility.measurement")
    if status == "SEMANTIC_UNAVAILABLE" and (feasibility.get("precision") is not None or feasibility.get("empirical_ceiling") is not None):
        raise BaselineContractError("unavailable feasibility result cannot claim a score")
    targets = _closed_mapping(report.get("target_derivation"), "pair report.target_derivation", _TARGET_KEYS)
    if targets.get("formula") != "max(program_floor + margin, baseline + realistic_gain)":
        raise BaselineContractError("target derivation formula is not frozen")
    for name in ("margin", "realistic_gain"):
        _number(targets.get(name), f"pair report.target_derivation.{name}")
    floor_values = _closed_mapping(targets.get("program_floor"), "pair report.target_derivation.program_floor", frozenset({"context_precision", "mandatory_recall", "mrr"}))
    target_values = _closed_mapping(targets.get("targets"), "pair report.target_derivation.targets", frozenset({"context_precision", "mandatory_recall", "mrr"}))
    for name in ("context_precision", "mandatory_recall", "mrr"):
        _number(floor_values.get(name), f"program_floor.{name}")
        target = _closed_mapping(target_values.get(name), f"targets.{name}", _TARGET_METRIC_KEYS)
        _number(target.get("value"), f"targets.{name}.value")
        _nonempty(target.get("status"), f"targets.{name}.status")
        _number(target.get("baseline"), f"targets.{name}.baseline", nullable=True)
    quality_visibility = _closed_mapping(targets.get("quality_visibility"), "pair report.target_derivation.quality_visibility", _QUALITY_VISIBILITY_KEYS)
    if quality_visibility.get("v2_must_exceed_v1") is not True or quality_visibility.get("promotion_allowed") is not False:
        raise BaselineContractError("target quality visibility must keep V2 shadow-only")
    _nonempty(quality_visibility.get("spike_status"), "quality_visibility.spike_status")

    # Mandatory recall is a distinct metric from context recall.  Bind the
    # recorded target baseline to the actual required-item counts so a report
    # cannot relabel an easier metric as mandatory coverage.
    v1_metrics = v1["metrics"]
    expected_baselines = {
        "context_precision": v1_metrics.get("context_precision"),
        "mandatory_recall": (
            float(v1_metrics["required_selected_items"]) / float(v1_metrics["required_items"])
            if v1_metrics.get("required_items") not in (None, 0) and v1_metrics.get("required_selected_items") is not None
            else None
        ),
        "mrr": None,
    }
    for name, expected in expected_baselines.items():
        recorded = target_values[name].get("baseline")
        if expected is None:
            if recorded is not None:
                raise BaselineContractError(f"targets.{name}.baseline claims an unavailable metric")
        elif recorded is None or abs(float(recorded) - float(expected)) > 1e-6:
            raise BaselineContractError(f"targets.{name}.baseline does not match V1 metrics")
    return dict(report)
