"""Versioned baseline snapshots preserve history and current compatibility."""

from __future__ import annotations

from pathlib import Path

from evals.baseline_snapshot import (
    BASELINE_ID,
    DEFAULT_BASELINE_PATH,
    DEFAULT_BASELINE_V1_MANIFEST,
    DEFAULT_BASELINE_V1_PATH,
    BASELINE_V1_ID,
    check_baseline_snapshot,
    check_historical_baseline,
    source_fingerprint,
)


ROOT = Path(__file__).resolve().parents[1]


def test_baseline_v1_is_verified_as_immutable_historical_evidence():
    report = check_historical_baseline(DEFAULT_BASELINE_V1_PATH, DEFAULT_BASELINE_V1_MANIFEST)

    assert report["source"]["baseline_id"] == BASELINE_V1_ID
    assert report["metrics"]["case_count"] == 101
    assert all(summary["state"] == "pass" for summary in report["invariants"].values())


def test_baseline_v2_snapshot_matches_current_public_suite_inputs():
    report = check_baseline_snapshot(DEFAULT_BASELINE_PATH, ROOT)

    assert report["source"]["baseline_id"] == BASELINE_ID
    assert report["source"]["source_fingerprint"] == source_fingerprint(ROOT)
    assert report["corpus"]["suite"] == "public"
    assert report["metrics"]["case_count"] == 130
    assert all(summary["state"] == "pass" for summary in report["invariants"].values())
