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


def test_package_legacy_and_summarizer_helpers_share_identity() -> None:
    legacy = importlib.import_module("scripts.anomaly_detector")
    bare_legacy = importlib.import_module("anomaly_detector")
    package_summarizer = importlib.import_module("brain_eleven.support.summarizer")

    assert PackagedAnomalyDetector is AnomalyDetector is legacy.AnomalyDetector
    assert PackagedAnomalyDetector is bare_legacy.AnomalyDetector
    assert tokenize is package_summarizer.tokenize
    assert jaccard_similarity is package_summarizer.jaccard_similarity
    assert legacy.tokenize is tokenize
    assert legacy.jaccard_similarity is jaccard_similarity


def test_legacy_anomaly_file_is_only_an_adapter() -> None:
    source_path = ROOT / "scripts" / "anomaly_detector.py"
    source = source_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    defined_classes = {
        node.name for node in ast.walk(tree) if isinstance(node, ast.ClassDef)
    }
    defined_functions = {
        node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)
    }

    assert "brain_eleven.support.anomaly" in source
    assert not defined_classes & {"AnomalyDetector"}
    assert not defined_functions & {
        "detect_all",
        "detect_duplicate_content",
        "detect_stale_open_loops",
        "detect_low_confidence_outliers",
        "detect_quality_confidence_gap",
        "detect_burst_ingestion",
        "detect_broken_supersession",
        "detect_trivial_content",
    }


def test_package_and_legacy_detectors_produce_matching_reports(tmp_path: Path) -> None:
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
    legacy = importlib.import_module("scripts.anomaly_detector")

    package_report = AnomalyDetector(str(tmp_path)).detect_all()
    legacy_report = legacy.AnomalyDetector(str(tmp_path)).detect_all()

    assert package_report["total_memories_scanned"] == 2
    assert package_report["by_severity"]["critical"] == 1
    assert {
        key: value for key, value in package_report.items() if key != "generated_at"
    } == {
        key: value for key, value in legacy_report.items() if key != "generated_at"
    }


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


def test_direct_execution_preserves_json_report_contract(tmp_path: Path) -> None:
    _write_memories(tmp_path, [])
    script = ROOT / "scripts" / "anomaly_detector.py"
    result = subprocess.run(
        [sys.executable, str(script), "--vault", str(tmp_path), "--json"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["total_memories_scanned"] == 0
    assert report["total_anomalies"] == 0
