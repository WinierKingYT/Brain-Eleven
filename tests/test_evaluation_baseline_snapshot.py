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


def test_source_fingerprint_is_independent_of_checkout_line_endings(tmp_path):
    source = tmp_path / "evals" / "corpus-v2"
    source.mkdir(parents=True)
    (source / "sample.json").write_bytes(b'{\r\n  "id": "same"\r\n}\r\n')
    (tmp_path / "evals" / "baseline.py").write_bytes(b"value = 1\r\n")
    (tmp_path / "evals" / "contracts.py").write_bytes(b"value = 2\r\n")
    (tmp_path / "evals" / "corpus_builder.py").write_bytes(b"value = 3\r\n")
    (tmp_path / "evals" / "fixture_generator.py").write_bytes(b"value = 4\r\n")
    (tmp_path / "evals" / "metrics.py").write_bytes(b"value = 5\r\n")
    (tmp_path / "evals" / "reporting.py").write_bytes(b"value = 6\r\n")
    (tmp_path / "evals" / "run.py").write_bytes(b"value = 7\r\n")
    (tmp_path / "evals" / "fixtures").mkdir()
    (tmp_path / "evals" / "fixtures" / "fixture.json").write_bytes(b"{}\r\n")
    (tmp_path / "evals" / "schemas").mkdir()
    (tmp_path / "evals" / "schemas" / "schema.json").write_bytes(b"{}\r\n")
    (tmp_path / "scripts").mkdir()
    for name in ("context-compiler.py", "memory_scope.py", "memory_store.py", "project_registry.py"):
        (tmp_path / "scripts" / name).write_bytes(b"value = 1\r\n")

    crlf_fingerprint = source_fingerprint(tmp_path)
    for path in tmp_path.rglob("*"):
        if path.is_file():
            path.write_bytes(path.read_bytes().replace(b"\r\n", b"\n"))

    assert source_fingerprint(tmp_path) == crlf_fingerprint
