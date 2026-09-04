"""Tests for truthful Phase 16 evidence construction."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from phase16_evidence import PASS, Phase16EvidenceError, REQUIRED_TESTS, build_manifest, main  # noqa: E402


def _write_junit(path: Path, *, failing: str | None = None) -> None:
    cases = "".join(
        f'<testcase name="{name}">{"<failure/>" if name == failing else ""}</testcase>'
        for name in sorted(REQUIRED_TESTS)
    )
    path.write_text(f"<testsuite>{cases}</testsuite>", encoding="utf-8")


def _write_evaluation(path: Path, *, leakage: float = 0.0) -> None:
    path.write_text(json.dumps({
        "provider": "task_state_v1",
        "suite": "all",
        "metrics": {"task_case_count": 28, "state_case_count": 28, "wrong_project_state_leakage_rate": leakage},
        "invariants": {"state_accuracy": {"state": "pass"}},
    }), encoding="utf-8")


def test_phase16_manifest_is_pass_only_for_runtime_backed_required_tests_and_evaluation(tmp_path):
    junit = tmp_path / "results.xml"
    evaluation = tmp_path / "task-state.json"
    _write_junit(junit)
    _write_evaluation(evaluation)

    manifest = build_manifest(junit, evaluation, tmp_path)

    assert manifest["status"] == PASS
    assert manifest["invariants"]["wrong_project_state_leakage"] == 0


def test_phase16_manifest_refuses_incomplete_or_leaking_evaluation_evidence(tmp_path):
    junit = tmp_path / "results.xml"
    evaluation = tmp_path / "task-state.json"
    _write_junit(junit)
    _write_evaluation(evaluation, leakage=0.1)

    with pytest.raises(Phase16EvidenceError, match="non-zero wrong-project"):
        build_manifest(junit, evaluation, tmp_path)


def test_phase16_evidence_cli_writes_a_runtime_manifest(tmp_path):
    junit, evaluation, output = tmp_path / "results.xml", tmp_path / "task-state.json", tmp_path / "phase16.json"
    _write_junit(junit)
    _write_evaluation(evaluation)

    assert main(["--junit", str(junit), "--evaluation", str(evaluation), "--output", str(output), "--root", str(ROOT)]) == 0
    assert json.loads(output.read_text(encoding="utf-8"))["status"] == PASS
