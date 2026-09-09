"""Fail-closed schema for the IG-01-B public, private, and failure corpora.

The schema is intentionally data-only.  A case records the evidence and the
ground truth that a future evaluator will consume; it does not run the system
under test or tune any production behavior.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

DATASET_CLASSES = frozenset({
    "PUBLIC_SYNTHETIC",
    "PRIVATE_REALISTIC",
    "SANITIZED_REAL_FAILURE",
})
LANGUAGES = frozenset({"tr", "en", "tr-en"})
SPLITS = frozenset({"dev", "validation", "holdout", "abstention"})
CASE_KINDS = frozenset({"answerable", "adversarial", "control", "abstention"})
PHENOMENA = (
    "explicit_decision",
    "preference",
    "lesson",
    "requirement",
    "suggestion",
    "hypothetical",
    "question",
    "negation",
    "correction",
    "quoted_material",
    "assistant_proposal",
    "old_critical_decision",
    "irrelevant_recent_memory",
    "wrong_project_candidate",
    "superseded_memory",
    "resolved_blocker",
    "ambiguous_reference",
)
FAMILIES = frozenset({"retrieval", "extraction", "reference_resolution"})

REQUIRED_FIELDS = frozenset({
    "case_id", "dataset_class", "corpus_version", "family", "category",
    "case_kind", "language", "split", "project_id", "query", "candidate_ids",
    "required_ids", "acceptable_ids", "forbidden_ids", "mandatory_ids",
    "rationale", "answerability", "provenance", "labels", "data_lineage",
    "contamination_class", "generator_identity", "sut_identity", "source_case_ids",
})


def _require_string(value: Any, field: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")


def _require_list(value: Any, field: str) -> None:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError(f"{field} must be a list of strings")


def validate_case(case: dict[str, Any], *, expected_class: str | None = None) -> None:
    """Validate one case and reject ambiguous or incomplete labels."""

    required = REQUIRED_FIELDS - ({"query"} if case.get("dataset_class") == "PRIVATE_REALISTIC" else set())
    if case.get("dataset_class") == "PRIVATE_REALISTIC":
        required = required | {"query_hash"}
    missing = required - set(case)
    if missing:
        raise ValueError(f"{case.get('case_id', '<unknown>')} missing fields: {sorted(missing)}")
    _require_string(case["case_id"], "case_id")
    if expected_class and case["dataset_class"] != expected_class:
        raise ValueError(f"{case['case_id']} has unexpected dataset class")
    if case["dataset_class"] not in DATASET_CLASSES:
        raise ValueError(f"{case['case_id']} has unknown dataset class")
    if case["family"] not in FAMILIES:
        raise ValueError(f"{case['case_id']} has unknown family")
    if case["category"] not in PHENOMENA:
        raise ValueError(f"{case['case_id']} has unknown category")
    if case["language"] not in LANGUAGES:
        raise ValueError(f"{case['case_id']} has unknown language")
    if case["case_kind"] not in CASE_KINDS:
        raise ValueError(f"{case['case_id']} has unknown case_kind")
    if case["split"] not in SPLITS:
        raise ValueError(f"{case['case_id']} has unknown split")
    _require_string(case["corpus_version"], "corpus_version")
    _require_string(case["contamination_class"], "contamination_class")
    _require_string(case["generator_identity"], "generator_identity")
    _require_string(case["sut_identity"], "sut_identity")
    _require_list(case["source_case_ids"], "source_case_ids")
    _require_string(case["project_id"], "project_id")
    if case["dataset_class"] == "PRIVATE_REALISTIC":
        _require_string(case["query_hash"], "query_hash")
    else:
        _require_string(case["query"], "query")
    for field in ("candidate_ids", "required_ids", "acceptable_ids", "forbidden_ids", "mandatory_ids"):
        _require_list(case[field], field)
    answerability = case["answerability"]
    if not isinstance(answerability, dict) or answerability.get("status") not in {"answerable", "unanswerable"}:
        raise ValueError(f"{case['case_id']} has invalid answerability")
    if not isinstance(answerability.get("reason"), str) or not answerability["reason"].strip():
        raise ValueError(f"{case['case_id']} answerability needs a reason")
    if (case["case_kind"] == "abstention") != (answerability["status"] == "unanswerable"):
        raise ValueError(f"{case['case_id']} case_kind/answerability mismatch")
    if case["case_kind"] != "abstention" and case["split"] == "abstention":
        raise ValueError(f"{case['case_id']} answerable case in abstention split")
    if set(case["required_ids"]) - set(case["candidate_ids"]):
        raise ValueError(f"{case['case_id']} required_ids must be candidate_ids")
    if set(case["mandatory_ids"]) - set(case["candidate_ids"]):
        raise ValueError(f"{case['case_id']} mandatory_ids must be candidate_ids")
    if set(case["forbidden_ids"]) & set(case["required_ids"]):
        raise ValueError(f"{case['case_id']} required and forbidden IDs overlap")
    provenance = case["provenance"]
    if not isinstance(provenance, dict):
        raise ValueError(f"{case['case_id']} provenance must be an object")
    for field in ("author", "generator", "label_owner", "source_id", "privacy_status", "created_at"):
        _require_string(provenance.get(field), f"provenance.{field}")
    if not isinstance(case["data_lineage"], dict) or not case["data_lineage"].get("lineage_id"):
        raise ValueError(f"{case['case_id']} data_lineage.lineage_id is required")
    if case["family"] == "extraction":
        conversation = case.get("conversation")
        if case["dataset_class"] != "PRIVATE_REALISTIC":
            if not isinstance(conversation, list) or not conversation:
                raise ValueError(f"{case['case_id']} extraction case needs conversation turns")
            if any(not isinstance(turn, dict) or turn.get("role") not in {"user", "assistant", "system"} or not isinstance(turn.get("text"), str) or not turn["text"].strip() for turn in conversation):
                raise ValueError(f"{case['case_id']} has invalid conversation turn")
        expected = case.get("expected")
        forbidden = case.get("forbidden")
        if not isinstance(expected, dict) or not isinstance(forbidden, dict):
            raise ValueError(f"{case['case_id']} extraction expected/forbidden labels are required")
        for field in ("commitment", "memory_type", "state_operation", "correction", "target_behavior", "scope", "source_role"):
            if field not in expected:
                raise ValueError(f"{case['case_id']} expected.{field} is required")
        for field in ("canonical_commit", "wrong_type", "false_commitment"):
            if field not in forbidden:
                raise ValueError(f"{case['case_id']} forbidden.{field} is required")
        if case["dataset_class"] != "PRIVATE_REALISTIC" and case["category"] == "assistant_proposal" and conversation[0]["role"] != "assistant":
            raise ValueError(f"{case['case_id']} assistant proposal must have assistant source role")
        if case["dataset_class"] != "PRIVATE_REALISTIC" and case["category"] == "quoted_material" and expected["source_role"] != "quoted_external":
            raise ValueError(f"{case['case_id']} quoted material needs quoted_external source role")
    labels = case["labels"]
    if not isinstance(labels, dict) or not labels.get("primary"):
        raise ValueError(f"{case['case_id']} needs primary ground-truth labels")
    confidence = labels.get("confidence")
    if confidence is not None:
        if not isinstance(confidence, dict) or any(not isinstance(value, (int, float)) or not 0 <= value <= 1 for value in confidence.values()):
            raise ValueError(f"{case['case_id']} has invalid label confidence")
    if case["split"] == "holdout":
        double = labels.get("double_annotation")
        if not isinstance(double, dict) or not isinstance(double.get("annotator_a"), dict) or not isinstance(double.get("annotator_b"), dict):
            raise ValueError(f"{case['case_id']} holdout case is not double-labeled")
        if double["annotator_a"].get("annotator_id") == double["annotator_b"].get("annotator_id"):
            raise ValueError(f"{case['case_id']} holdout annotators must be distinct")
        if not double.get("adjudicated") or "disagreement" not in double:
            raise ValueError(f"{case['case_id']} holdout adjudication is incomplete")


def load_cases(path: Path, *, expected_class: str | None = None) -> list[dict[str, Any]]:
    """Load JSONL cases and validate every record before returning it."""

    cases: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_number} invalid JSON: {exc}") from exc
            if not isinstance(value, dict):
                raise ValueError(f"{path}:{line_number} case must be an object")
            validate_case(value, expected_class=expected_class)
            cases.append(value)
    if not cases:
        raise ValueError(f"{path} contains no cases")
    ids = [case["case_id"] for case in cases]
    if len(ids) != len(set(ids)):
        raise ValueError(f"{path} contains duplicate case IDs")
    return cases


def iter_jsonl(paths: Iterable[Path]) -> Iterable[dict[str, Any]]:
    for path in paths:
        yield from load_cases(path)
