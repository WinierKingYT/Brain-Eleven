"""Sanitized real-failure format reserved for IG-08 dogfood ingestion.

The directory is intentionally empty in IG-01-B.  This module provides a
strict, content-minimizing ingestion boundary so future failures cannot be
copied from raw prompts into the repository by accident.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

FAILURE_TAXONOMY = frozenset({
    "CAPTURE_MISS", "FALSE_CAPTURE", "WRONG_TYPE", "WRONG_SCOPE", "WRONG_TARGET",
    "FALSE_SUPERSESSION", "RETRIEVAL_MISS", "RETRIEVAL_NOISE", "AUTHORITY_ERROR",
    "STALE_CONTEXT", "TOKEN_WASTE",
})
RAW_FIELDS = frozenset({"prompt", "transcript", "memory_content", "token", "secret", "raw_text", "query", "conversation", "text", "content"})
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


def validate_failure_case(case: dict[str, Any]) -> None:
    missing = REQUIRED_FIELDS - set(case)
    if missing:
        raise ValueError(f"failure case missing fields: {sorted(missing)}")
    if case["taxonomy"] not in FAILURE_TAXONOMY:
        raise ValueError(f"unknown failure taxonomy: {case['taxonomy']}")
    if case["sanitized"] is not True:
        raise ValueError("real failures must be explicitly sanitized")
    _reject_raw_fields(case)
    for field in ("failure_id", "corpus_version", "project_hash", "task_hash", "root_cause"):
        if not isinstance(case[field], str) or not case[field].strip():
            raise ValueError(f"{field} must be a non-empty string")
    if not isinstance(case["provenance"], dict) or not case["provenance"].get("source"):
        raise ValueError("failure provenance.source is required")
    if not isinstance(case["sanitization"], list) or not case["sanitization"]:
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
