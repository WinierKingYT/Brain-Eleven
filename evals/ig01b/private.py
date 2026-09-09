"""Local-only PRIVATE_REALISTIC corpus storage with repository path guards."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .integrity import assert_private_path
from .schema import REQUIRED_FIELDS, validate_case

_RAW_KEYS = frozenset({
    "prompt", "raw_prompt", "transcript", "raw_transcript", "raw_text", "memory_content",
    "raw_memory", "token", "secret", "password", "query", "raw_query", "conversation",
    "text", "content", "free_text", "diagnostic", "details", "message",
})
PRIVATE_ALLOWED_ROOT_KEYS = frozenset((set(REQUIRED_FIELDS) - {"query"}) | {
    "query_hash", "evidence_refs", "expected", "forbidden", "labels",
})
SAFE_HASH = re.compile(r"sha256:[0-9a-f]{64}")
SAFE_TEXT_KEYS = frozenset({"rationale", "reason"})
SAFE_TEXT_VALUES = frozenset({"fixture-label", "hash-only", "redacted"})
SAFE_TOKEN_KEYS = frozenset({
    "author", "generator", "label_owner", "source_id", "privacy_status", "created_at",
    "lineage_id", "event_time", "ingested_at", "annotator_id", "method", "protocol",
})
SAFE_TOKEN = re.compile(r"[A-Za-z0-9_.:/+-]{1,128}")
SAFE_PROVENANCE_SOURCE = re.compile(r"(?:dogfood-turn-hash|manual-review|synthetic-regression|ig08-dogfood|sha256:[0-9a-f]{64})")
_SAFE_NESTED_KEYS = frozenset({
    "primary", "confidence", "double_annotation", "annotator_a", "annotator_b", "adjudicated",
    "category", "expected_memory_type", "memory_type", "commitment", "temporal", "scope", "lifecycle",
    "abstain", "correction", "correction_target", "state_operation", "target_behavior", "source_role",
    "status", "canonical_commit", "false_commitment", "wrong_type",
    "annotator_id", "method", "label", "disagreement", "protocol", "lineage_id", "event_time",
    "ingested_at", "author", "generator", "label_owner", "source_id", "privacy_status", "created_at",
    "reason", "source",
})


def _assert_content_free(value: Any, path: str = "case", key: str | None = None) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if path == "case" and str(key) not in PRIVATE_ALLOWED_ROOT_KEYS:
                raise ValueError(f"private realistic data contains unapproved root field: {path}.{key}")
            if str(key).lower() in _RAW_KEYS:
                raise ValueError(f"private realistic data contains forbidden raw field: {path}.{key}")
            if path != "case" and str(key) not in _SAFE_NESTED_KEYS:
                raise ValueError(f"private realistic data contains unapproved free-text field: {path}.{key}")
            _assert_content_free(child, f"{path}.{key}", str(key))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _assert_content_free(child, f"{path}[{index}]", key)
    elif isinstance(value, str):
        if key in {"project_id", "query_hash"} and not SAFE_HASH.fullmatch(value):
            raise ValueError(f"private realistic {key} must be a sha256 hash")
        if key in SAFE_TEXT_KEYS and value not in SAFE_TEXT_VALUES and not SAFE_HASH.fullmatch(value):
            raise ValueError(f"private realistic {key} contains unapproved free-text; must be redacted or hashed")
        if key == "source" and not SAFE_PROVENANCE_SOURCE.fullmatch(value):
            raise ValueError("private realistic provenance.source must be a bounded code or hash")
        if not value:
            return
        if not SAFE_TOKEN.fullmatch(value) and key not in SAFE_TEXT_KEYS:
            raise ValueError(f"private realistic {key} must be a bounded token")
        if len(value) > 256 or any(char in value for char in "\r\n"):
            raise ValueError(f"private realistic data contains unbounded text: {path}")


def private_root(repository_root: Path) -> Path:
    root = (repository_root / "evals" / "private").resolve()
    assert_private_path(root, repository_root)
    root.mkdir(parents=True, exist_ok=True)
    return root


def write_private_case(repository_root: Path, case: dict[str, Any]) -> Path:
    """Write sanitized local data only; callers must remove raw prompt content."""

    if case.get("dataset_class") != "PRIVATE_REALISTIC":
        raise ValueError("private case must declare dataset_class=PRIVATE_REALISTIC")
    _assert_content_free(case)
    validate_case(case)
    root = private_root(repository_root)
    case_id = case.get("case_id")
    if not isinstance(case_id, str) or not case_id or any(char in case_id for char in "/\\"):
        raise ValueError("private case_id must be a safe filename component")
    path = root / f"{case_id}.json"
    assert_private_path(path, repository_root)
    path.write_text(json.dumps(case, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def repository_leak_candidates(repository_root: Path) -> list[Path]:
    """Return files that would be a private-corpus leak if tracked or public."""

    candidates: list[Path] = []
    for path in repository_root.rglob("*"):
        if not path.is_file():
            continue
        lowered = path.as_posix().lower()
        if "private_realistic" in lowered or "/evals/private/" in lowered:
            candidates.append(path)
    return candidates
