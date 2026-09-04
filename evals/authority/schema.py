"""Strict contracts for synthetic, metadata-first authority expectations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


SCHEMA_VERSION = 1
SUITES = frozenset({"public", "holdout"})
CATEGORIES = frozenset(
    {
        "supersession", "duplicate", "scope_isolation", "lifecycle",
        "implementation_gap", "incomplete_provenance", "determinism", "state_current",
    }
)


class AuthorityCorpusError(ValueError):
    """A synthetic authority expectation is not coherent or reproducible."""


@dataclass(frozen=True)
class AuthorityExpectation:
    case_id: str
    suite: str
    category: str
    expected_statuses: Mapping[str, str]


def parse_expectation(document: Mapping[str, Any]) -> AuthorityExpectation:
    if not isinstance(document, Mapping) or set(document) != {"schema_version", "case_id", "suite", "category", "expected_statuses"}:
        raise AuthorityCorpusError("authority expectation has invalid fields")
    if document.get("schema_version") != SCHEMA_VERSION:
        raise AuthorityCorpusError("authority expectation schema_version must be 1")
    case_id = document["case_id"]
    suite = document["suite"]
    category = document["category"]
    statuses = document["expected_statuses"]
    if not isinstance(case_id, str) or not case_id:
        raise AuthorityCorpusError("authority case_id must be non-empty")
    if suite not in SUITES:
        raise AuthorityCorpusError("authority suite is unsupported")
    if category not in CATEGORIES:
        raise AuthorityCorpusError("authority category is unsupported")
    if not isinstance(statuses, Mapping) or not statuses:
        raise AuthorityCorpusError("authority expected_statuses must be non-empty")
    normalized = {}
    for key, value in statuses.items():
        if not isinstance(key, str) or not key or not isinstance(value, str) or not value:
            raise AuthorityCorpusError("authority expected_statuses is malformed")
        normalized[key] = value
    return AuthorityExpectation(case_id, suite, category, dict(sorted(normalized.items())))
