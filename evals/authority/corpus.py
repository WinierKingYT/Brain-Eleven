"""Deterministic public/holdout metadata-first authority scenarios."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .schema import AuthorityExpectation, parse_expectation


PUBLIC_COUNTS = {
    "supersession": 30,
    "duplicate": 25,
    "scope_isolation": 25,
    "lifecycle": 20,
    "implementation_gap": 15,
    "incomplete_provenance": 15,
    "determinism": 10,
    "state_current": 10,
}
HOLDOUT_COUNTS = {
    "supersession": 5,
    "duplicate": 5,
    "scope_isolation": 5,
    "lifecycle": 5,
    "implementation_gap": 5,
    "incomplete_provenance": 5,
}
DEFAULT_SIDECAR = Path(__file__).with_name("expectation-sidecar.json")


_EXPECTED = {
    "supersession": {"old": "SUPERSEDED", "new": "AUTHORITATIVE"},
    "duplicate": {"first": "AUTHORITATIVE", "second": "SUPPORTING"},
    "scope_isolation": {"foreign_candidate": "ABSENT"},
    "lifecycle": {"historical": "HISTORICAL"},
    "implementation_gap": {"blocker": "IMPLEMENTATION_GAP", "old": "IMPLEMENTATION_GAP"},
    "incomplete_provenance": {"unknown": "SUPPORTING"},
    "determinism": {"result": "DETERMINISTIC"},
    "state_current": {"objective": "AUTHORITATIVE"},
}


def _documents(suite: str, counts: dict[str, int]) -> tuple[AuthorityExpectation, ...]:
    documents: list[AuthorityExpectation] = []
    for category, count in counts.items():
        for index in range(1, count + 1):
            documents.append(
                parse_expectation(
                    {
                        "schema_version": 1,
                        "case_id": f"authority_{suite}_{category}_{index:03d}",
                        "suite": suite,
                        "category": category,
                        "expected_statuses": _EXPECTED[category],
                    }
                )
            )
    return tuple(documents)


def expectations(suite: str) -> tuple[AuthorityExpectation, ...]:
    if suite == "public":
        return _documents("public", PUBLIC_COUNTS)
    if suite == "holdout":
        return _documents("holdout", HOLDOUT_COUNTS)
    if suite == "smoke":
        return _documents("public", {category: 1 for category in PUBLIC_COUNTS})
    if suite == "all":
        return expectations("public") + expectations("holdout")
    raise ValueError(f"unsupported authority suite: {suite}")


def load_sidecar(path: Path | str = DEFAULT_SIDECAR) -> dict[str, Any]:
    """Load the versioned corpus contract before accepting generated cases."""
    try:
        document = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"authority sidecar is unreadable: {path}") from exc
    required = {
        "schema_version", "corpus_version", "public_case_count", "holdout_case_count",
        "privacy", "metadata_first", "semantic_prose_conflict",
    }
    if not isinstance(document, dict) or set(document) != required:
        raise ValueError("authority sidecar has invalid fields")
    if document["schema_version"] != 1 or document["corpus_version"] != 1:
        raise ValueError("authority sidecar schema is unsupported")
    if document["public_case_count"] != 150 or document["holdout_case_count"] != 30:
        raise ValueError("authority sidecar corpus cardinality is invalid")
    if document["privacy"] != "synthetic_only" or document["metadata_first"] is not True:
        raise ValueError("authority sidecar weakens the privacy or metadata-first contract")
    if document["semantic_prose_conflict"] != "abstain_or_unresolved":
        raise ValueError("authority sidecar semantic conflict policy is invalid")
    return document


def validate_corpus() -> dict[str, Any]:
    load_sidecar()
    public = expectations("public")
    holdout = expectations("holdout")
    all_ids = [case.case_id for case in public + holdout]
    if len(public) != 150 or len(holdout) != 30 or len(all_ids) != len(set(all_ids)):
        raise ValueError("authority corpus cardinality or identity contract is invalid")
    return {"public": len(public), "holdout": len(holdout), "total": len(all_ids)}
