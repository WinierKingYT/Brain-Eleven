"""Contract and parity tests for the IG-07 anomaly migration."""

from __future__ import annotations

import ast
import importlib
import json
import subprocess
import sys
from pathlib import Path

from brain_eleven.support import AnomalyDetector as PackagedAnomalyDetector
from brain_eleven.support.anomaly import AnomalyDetector, jaccard_similarity, tokenize


ROOT = Path(__file__).resolve().parents[1]


def _write_memories(vault: Path, memories: list[dict]) -> None:
    claude_dir = vault / ".claude"
    claude_dir.mkdir(exist_ok=True)
    (claude_dir / "validated-memory.json").write_text(
        json.dumps({"validated_memory": memories}),
        encoding="utf-8",
    )


def test_package_and_summarizer_helpers_share_identity() -> None:
    package_summarizer = importlib.import_module("brain_eleven.support.summarizer")

    assert PackagedAnomalyDetector is AnomalyDetector
    assert tokenize is package_summarizer.tokenize
    assert jaccard_similarity is package_summarizer.jaccard_similarity


def test_detector_reports_broken_supersession_and_trivial_content(tmp_path: Path) -> None:
    memories = [
        {
            "memory_id": "broken",
            "type": "decision",
            "content": "A decision with a missing supersession target",
            "status": "active",
            "superseded_by": "missing",
        },
        {
            "memory_id": "short",
            "type": "observation",
            "content": "ok",
            "status": "active",
        },
    ]
    _write_memories(tmp_path, memories)
    package_report = AnomalyDetector(str(tmp_path)).detect_all()

    assert package_report["total_memories_scanned"] == 2
    assert package_report["by_severity"]["critical"] == 1


def test_malformed_timestamp_and_sparse_memory_are_safe() -> None:
    detector = AnomalyDetector()
    malformed_timestamp = {
        "memory_id": "bad-date",
        "type": "open_loop",
        "status": "active",
        "timestamp": "not-a-timestamp",
    }
    sparse_memory = {"memory_id": "sparse"}

    assert detector.detect_stale_open_loops([malformed_timestamp]) == []
    report = detector.detect_all([sparse_memory])
    assert report["total_memories_scanned"] == 1
    assert report["total_anomalies"] == 1
    assert report["anomalies"][0]["type"] == "trivial_content"


