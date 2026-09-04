"""The committed baseline must be a current deterministic evaluation result."""

from __future__ import annotations

from pathlib import Path

from evals.baseline_snapshot import (
    BASELINE_ID,
    DEFAULT_BASELINE_PATH,
    check_baseline_snapshot,
    source_fingerprint,
)


ROOT = Path(__file__).resolve().parents[1]


def test_baseline_v1_snapshot_matches_current_public_suite_inputs():
    report = check_baseline_snapshot(DEFAULT_BASELINE_PATH, ROOT)

    assert report["source"]["baseline_id"] == BASELINE_ID
    assert report["source"]["source_fingerprint"] == source_fingerprint(ROOT)
    assert report["corpus"]["suite"] == "public"
    assert report["metrics"]["case_count"] == 101
    assert all(summary["state"] == "pass" for summary in report["invariants"].values())
