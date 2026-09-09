"""Sanitized real-failure format reserved for IG-08 dogfood ingestion.

The directory is intentionally empty in IG-01-B.  This module provides a
strict, content-minimizing ingestion boundary so future failures cannot be
copied from raw prompts into the repository by accident.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

FAILURE_TAXONOMY = frozenset({
    "CAPTURE_MISS", "FALSE_CAPTURE", "WRONG_TYPE", "WRONG_SCOPE", "WRONG_TARGET",
    "FALSE_SUPERSESSION", "RETRIEVAL_MISS", "RETRIEVAL_NOISE", "AUTHORITY_ERROR",
    "STALE_CONTEXT", "TOKEN_WASTE",
})
RAW_FIELDS = frozenset({"prompt", "transcript", "memory_content", "token", "secret", "raw_text", "query", "conversation", "text", "content"})
FAILURE_ROOT_CAUSES = frozenset({
    "capture_boundary", "event_delivery", "worker_crash", "idempotency", "queue_corruption",
    "evidence_missing", "extraction_classifier", "state_routing", "authority_resolution",
    "reference_resolution", "ranking_signal", "scope_filter", "lifecycle_filter",
    "context_budget", "provider_unavailable", "configuration", "unknown",
})
SAFE_EXPECTED_ACTUAL_KEYS = frozenset({
    "required_ids", "acceptable_ids", "forbidden_ids", "mandatory_ids", "selected_ids",
    "memory_ids", "memory_type", "state_operation", "target_behavior", "scope", "lifecycle",
    "category", "commitment", "status", "reason_code", "hash", "count",
})
SAFE_SANITIZATION_STEPS = frozenset({
    "remove_raw_prompt", "remove_transcript", "remove_memory_content", "hash_project",
    "hash_task", "strip_secrets", "strip_pii", "drop_free_text",
})
SAFE_PROVENANCE_KEYS = frozenset({"source", "source_id", "reviewer_id", "created_at"})
SAFE_TOKEN = re.compile(r"[A-Za-z0-9_.:/+-]{1,128}")
REQUIRED_FIELDS = frozenset({
    "failure_id", "taxonomy", "corpus_version", "sanitized", "project_hash",
    "task_hash", "expected", "actual", "root_cause", "provenance", "sanitization",
})


def _reject_raw_fields(value: Any, path: str = "case") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if str(key).lower() in RAW_FIELDS:
                raise ValueError(f"raw prompt or memory fields are forbidden: {path}.{key}")
            _reject_raw_fields(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _reject_raw_fields(child, f"{path}[{index}]")


def _validate_safe_metadata(value: Any, path: str) -> None:
    """Permit only bounded machine-readable expected/actual metadata."""

    if isinstance(value, dict):
        unknown = set(value) - SAFE_EXPECTED_ACTUAL_KEYS
        if unknown:
            raise ValueError(f"{path} contains an unapproved free-text field: {sorted(unknown)}")
        for key, child in value.items():
            _validate_safe_metadata(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _validate_safe_metadata(child, f"{path}[{index}]")
    elif isinstance(value, str):
        if len(value) > 128 or any(char in value for char in "\r\n"):
            raise ValueError(f"{path} contains unbounded free text")
        if value and not re.fullmatch(r"[A-Za-z0-9_.:/+-]+", value):
            raise ValueError(f"{path} contains unapproved free text")
    elif not isinstance(value, (bool, int, float)) and value is not None:
        raise ValueError(f"{path} contains an unsupported metadata value")


def validate_failure_case(case: dict[str, Any]) -> None:
    unknown = set(case) - REQUIRED_FIELDS
    if unknown:
        raise ValueError(f"failure case contains unapproved fields: {sorted(unknown)}")
    missing = REQUIRED_FIELDS - set(case)
    if missing:
        raise ValueError(f"failure case missing fields: {sorted(missing)}")
    if case["taxonomy"] not in FAILURE_TAXONOMY:
        raise ValueError(f"unknown failure taxonomy: {case['taxonomy']}")
    if case["sanitized"] is not True:
        raise ValueError("real failures must be explicitly sanitized")
    _reject_raw_fields(case)
    for section in ("expected", "actual"):
        value = case[section]
        if not isinstance(value, dict):
            raise ValueError(f"{section} contains an unapproved free-text field")
        _validate_safe_metadata(value, section)
    for field in ("failure_id", "corpus_version", "project_hash", "task_hash", "root_cause"):
        if not isinstance(case[field], str) or not case[field].strip():
            raise ValueError(f"{field} must be a non-empty string")
    for field in ("failure_id", "corpus_version"):
        if not SAFE_TOKEN.fullmatch(case[field]):
            raise ValueError(f"{field} must be a bounded token")
    for field in ("project_hash", "task_hash"):
        if not re.fullmatch(r"sha256:[0-9a-f]{64}", case[field]):
            raise ValueError(f"{field} must be a sha256 hash")
    if case["root_cause"] not in FAILURE_ROOT_CAUSES and not re.fullmatch(r"sha256:[0-9a-f]{64}", case["root_cause"]):
        raise ValueError("root_cause must be a controlled code or sha256 hash")
    provenance = case["provenance"]
    if not isinstance(provenance, dict) or set(provenance) - SAFE_PROVENANCE_KEYS:
        raise ValueError("failure provenance contains unapproved fields")
    source = provenance.get("source")
    if not isinstance(source, str) or not re.fullmatch(r"(?:dogfood-turn-hash|manual-review|synthetic-regression|ig08-dogfood|sha256:[0-9a-f]{64})", source):
        raise ValueError("failure provenance.source is required")
    for field, value in provenance.items():
        if field == "source":
            continue
        if not isinstance(value, str) or not SAFE_TOKEN.fullmatch(value):
            raise ValueError(f"failure provenance.{field} must be a bounded token")
    if not isinstance(case["sanitization"], list) or not case["sanitization"] or any(step not in SAFE_SANITIZATION_STEPS for step in case["sanitization"]):
        raise ValueError("sanitization steps are required")


def ingest_failure(case: dict[str, Any], repository_root: Path) -> Path:
    """Validate and write one sanitized failure to the IG-08-reserved area."""

    validate_failure_case(case)
    target_root = (repository_root / "evals" / "ig01b" / "failures").resolve()
    target_root.mkdir(parents=True, exist_ok=True)
    failure_id = case["failure_id"]
    if any(char in failure_id for char in "/\\"):
        raise ValueError("failure_id cannot contain path separators")
    path = target_root / f"{failure_id}.json"
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(case, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)
    return path


def empty_manifest() -> dict[str, Any]:
    return {
        "dataset_class": "SANITIZED_REAL_FAILURE",
        "corpus_version": "ig-failures-v1",
        "status": "EMPTY_RESERVED_FOR_IG-08",
        "cases": 0,
        "privacy": "sanitized-only-no-raw-content",
        "ingestion": "evals.ig01b.failures.ingest_failure",
        "taxonomy": sorted(FAILURE_TAXONOMY),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate/ingest a sanitized IG-08 failure case")
    parser.add_argument("case", type=Path)
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    case = json.loads(args.case.read_text(encoding="utf-8"))
    print(ingest_failure(case, args.repository_root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
