"""Tests for evaluation-only D0 rethink probes."""
from __future__ import annotations

import json
from pathlib import Path

from evals.ig01d.d0_rethink import (
    D0_RETRIEVAL_CORPUS,
    D0_RETRIEVAL_METADATA,
    FIXTURE_PATH,
    _ig01b_census,
    _load_versioned_retrieval_cases,
    _rrf,
    _scope_safe,
)


def test_ig01b_dev_language_strata_are_explicit_and_balanced():
    census = _ig01b_census()
    assert census["case_count"] == 76
    assert census["answerable_case_count"] == 76
    assert census["language_counts"] == {"en": 25, "tr": 26, "tr-en": 25}
    assert census["language_balance_min_fraction"] >= 0.25
    assert census["status"] == "BALANCED_LANGUAGE_STRATA_CASE_COUNT_BELOW_TARGET"


def test_rrf_is_deterministic_and_rewards_overlap():
    assert _rrf(["semantic-a", "shared"], ["shared", "lexical-b"]) == [
        "shared",
        "semantic-a",
        "lexical-b",
    ]


def test_scope_normalizes_empty_project_as_global_without_merging_lifecycle():
    assert _scope_safe({"project_id": "", "status": "active"}, "project-alpha")
    assert _scope_safe({"project_id": None, "status": "active"}, "project-alpha")
    assert not _scope_safe({"project_id": "project-beta", "status": "active"}, "project-alpha")
    assert _scope_safe({"project_id": "project-alpha", "status": "superseded"}, "project-alpha")


def test_d0_versioned_retrieval_fixture_is_balanced_and_schema_valid():
    documents, (_, tasks) = _load_versioned_retrieval_cases(
        D0_RETRIEVAL_CORPUS,
        D0_RETRIEVAL_METADATA,
        FIXTURE_PATH,
    )
    metadata = json.loads(Path(D0_RETRIEVAL_METADATA).read_text(encoding="utf-8"))
    counts = {language: 0 for language in ("en", "tr", "tr-en")}
    for document in documents:
        counts[metadata[document["task_id"]]["language"]] += 1
    assert len(tasks) == len(documents) == 120
    assert counts == {"en": 40, "tr": 40, "tr-en": 40}
    assert all("holdout" not in task.task_id.lower() for task in tasks)
