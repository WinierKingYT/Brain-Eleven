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


def _validate_metrics(metrics: Any, field: str) -> None:
    metrics = _mapping(metrics, field)
    if metrics.get("case_count", 0) <= 0:
        raise BaselineContractError(f"{field}.case_count must be positive")
    for name in (
        "context_precision", "context_recall", "selected_items", "relevant_selected_items",
        "required_items", "required_selected_items", "wrong_project_leakage_rate",
        "forbidden_context_rate", "superseded_leakage_rate", "resolved_leakage_rate",
        "unlabeled_context_rate",
    ):
        if name in metrics:
            _number(metrics[name], f"{field}.{name}", nullable=True)


def validate_baseline_report(report: Mapping[str, Any]) -> dict[str, Any]:
    """Validate one provider report without accepting raw benchmark content."""

    _safe_tree(report)
    report = _mapping(report, "report")
    if report.get("schema_version") != IG01D_SCHEMA_VERSION:
        raise BaselineContractError("unsupported IG01-D report schema")
    if report.get("report_type") != REPORT_TYPE:
        raise BaselineContractError("unsupported IG01-D report type")
    if report.get("evaluator_version") != EVALUATOR_VERSION:
        raise BaselineContractError("report.evaluator_version does not match the frozen evaluator")
    provider = _mapping(report.get("provider"), "report.provider")
    provider_id = _id(provider.get("id"), "report.provider.id")
    if provider_id not in {"context_compiler_baseline_v1", "context_compiler_v2"}:
        raise BaselineContractError("report.provider.id is not an IG01-D provider")
    corpus = _mapping(report.get("corpus"), "report.corpus")
    _id(corpus.get("fixture_id"), "report.corpus.fixture_id")
    if corpus.get("suite") != "public":
        raise BaselineContractError("IG01-D reports must use the public suite")
    if corpus.get("split") != ["dev", "test"]:
        raise BaselineContractError("IG01-D reports must use exactly DEV+TEST")
    task_ids = _task_ids(corpus.get("task_ids"), "report.corpus.task_ids")
    if corpus.get("task_count") != len(task_ids):
        raise BaselineContractError("report.corpus.task_count does not match task_ids")
    _fingerprint(corpus.get("split_fingerprint"), "report.corpus.split_fingerprint")
    source = _mapping(report.get("source"), "report.source")
    _sha(source.get("git_sha"), "report.source.git_sha")
    _fingerprint(source.get("evaluation_source_fingerprint"), "report.source.evaluation_source_fingerprint")
    _nonempty(source.get("corpus_version"), "report.source.corpus_version")
    _nonempty(source.get("evaluator_version"), "report.source.evaluator_version")
    if source.get("seed") != 17 or source.get("noise_count") != 24:
        raise BaselineContractError("report source must use the frozen IG01-D seed/noise configuration")
    _validate_metrics(report.get("metrics"), "report.metrics")
    if not isinstance(report.get("invariants"), Mapping):
        raise BaselineContractError("report.invariants must be an object")
    measurement = _mapping(report.get("measurement"), "report.measurement")
    _number(measurement.get("elapsed_ms"), "report.measurement.elapsed_ms")
    if measurement.get("case_count") != len(task_ids):
        raise BaselineContractError("measurement.case_count does not match task_ids")
    cases = report.get("cases")
    if not isinstance(cases, list) or len(cases) != len(task_ids):
        raise BaselineContractError("report.cases must contain one row per task")
    case_ids = [case.get("task_id") if isinstance(case, Mapping) else None for case in cases]
    if case_ids != task_ids:
        raise BaselineContractError("report.cases must be ordered by task_id")
    return dict(report)


def validate_pair_report(report: Mapping[str, Any]) -> dict[str, Any]:
    """Validate paired V1/V2 evidence and all same-input guarantees."""

    _safe_tree(report)
    report = _mapping(report, "pair report")
    if report.get("schema_version") != IG01D_SCHEMA_VERSION:
        raise BaselineContractError("unsupported IG01-D pair schema")
    if report.get("report_type") != PAIR_REPORT_TYPE:
        raise BaselineContractError("unsupported IG01-D pair report type")
    if report.get("evaluator_version") != EVALUATOR_VERSION:
        raise BaselineContractError("pair report.evaluator_version does not match the frozen evaluator")
    source = _mapping(report.get("source"), "pair report.source")
    _sha(source.get("git_sha"), "pair report.source.git_sha")
    _fingerprint(source.get("evaluation_source_fingerprint"), "pair report.source.evaluation_source_fingerprint")
    if source.get("seed") != 17 or source.get("noise_count") != 24:
        raise BaselineContractError("pair report uses an unfrozen seed/noise configuration")
    corpus = _mapping(report.get("corpus"), "pair report.corpus")
    if corpus.get("suite") != "public" or corpus.get("split") != ["dev", "test"]:
        raise BaselineContractError("pair report must be public DEV+TEST only")
    task_ids = _task_ids(corpus.get("task_ids"), "pair report.corpus.task_ids")
    _fingerprint(corpus.get("split_fingerprint"), "pair report.corpus.split_fingerprint")
    providers = _mapping(report.get("providers"), "pair report.providers")
    if set(providers) != set(PROVIDER_KEYS):
        raise BaselineContractError("pair report must contain v1 and v2")
    v1 = validate_baseline_report(providers["v1"])
    v2 = validate_baseline_report(providers["v2"])
    for label, provider in (("v1", v1), ("v2", v2)):
        provider_corpus = provider["corpus"]
        if provider_corpus["task_ids"] != task_ids:
            raise BaselineContractError(f"{label} task IDs differ from pair task IDs")
        if provider_corpus["split_fingerprint"] != corpus["split_fingerprint"]:
            raise BaselineContractError(f"{label} corpus fingerprint differs")
        provider_source = provider["source"]
        for key in ("git_sha", "corpus_version", "evaluator_version", "seed", "noise_count"):
            if provider_source.get(key) != source.get(key):
                raise BaselineContractError(f"{label} source.{key} differs from pair source")
    comparison = _mapping(report.get("comparison"), "pair report.comparison")
    if comparison.get("baseline") != {"provider_id": v1["provider"]["id"]}:
        raise BaselineContractError("comparison baseline does not identify V1")
    if comparison.get("candidate") != {"provider_id": v2["provider"]["id"]}:
        raise BaselineContractError("comparison candidate does not identify V2")
    measurement = _mapping(report.get("measurement"), "pair report.measurement")
    for name in ("v1_elapsed_ms", "v2_elapsed_ms"):
        _number(measurement.get(name), f"pair report.measurement.{name}")
    feasibility = _mapping(report.get("feasibility"), "pair report.feasibility")
    _nonempty(feasibility.get("status"), "pair report.feasibility.status")
    if feasibility.get("holdout_included") is not False:
        raise BaselineContractError("feasibility probe must explicitly exclude HOLDOUT")
    targets = _mapping(report.get("target_derivation"), "pair report.target_derivation")
    if targets.get("formula") != "max(program_floor + margin, baseline + realistic_gain)":
        raise BaselineContractError("target derivation formula is not frozen")
    for name in ("margin", "realistic_gain"):
        _number(targets.get(name), f"pair report.target_derivation.{name}")
    floor_values = _mapping(targets.get("program_floor"), "pair report.target_derivation.program_floor")
    target_values = _mapping(targets.get("targets"), "pair report.target_derivation.targets")
    for name in ("context_precision", "mandatory_recall", "mrr"):
        _number(floor_values.get(name), f"program_floor.{name}")
        target = _mapping(target_values.get(name), f"targets.{name}")
        _number(target.get("value"), f"targets.{name}.value")
        _nonempty(target.get("status"), f"targets.{name}.status")
    return dict(report)
