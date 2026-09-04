"""The graduation corpus is a deterministic, public, synthetic V2 fixture."""

from __future__ import annotations

from collections import Counter
from pathlib import Path

from evals.corpus_v2_builder import (
    DEFAULT_CORPUS_ROOT,
    EXPECTED_SUITE_COUNTS,
    EXPECTED_TASK_COUNT,
    TAXONOMY,
    check_corpus_v2,
    corpus_v2_manifest,
)
from evals.schema import load_fixture, load_tasks


ROOT = Path(__file__).resolve().parents[1]
FIXTURE_PATH = ROOT / "evals" / "fixtures" / "phase15-contract.json"


def test_corpus_v2_is_committed_exactly_with_70_60_30_boundaries():
    fixture = load_fixture(FIXTURE_PATH)
    check_corpus_v2(DEFAULT_CORPUS_ROOT, fixture)
    tasks = load_tasks(sorted(DEFAULT_CORPUS_ROOT.glob("**/p15_*.json")), fixture)

    assert len(tasks) == EXPECTED_TASK_COUNT == 160
    assert Counter(path.parent.name for path in DEFAULT_CORPUS_ROOT.glob("**/p15_*.json")) == EXPECTED_SUITE_COUNTS


def test_corpus_v2_manifest_covers_the_required_taxonomy_and_privacy_boundary():
    manifest = corpus_v2_manifest()

    assert manifest["task_count"] == 160
    assert set(TAXONOMY).issubset(manifest["taxonomy"])
    assert manifest["languages"] == ["turkish", "english", "mixed"]
    assert manifest["privacy"] == "synthetic_only"
