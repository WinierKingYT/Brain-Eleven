"""Truthfulness checks for Phase 18 graduation evidence."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from phase18_evidence import PASS, Phase18EvidenceError, REQUIRED_TESTS, build_manifest, main  # noqa: E402


def _write(path: Path, document: dict) -> None:
    path.write_text(json.dumps(document), encoding="utf-8")


def _junit(path: Path) -> None:
    path.write_text("<testsuite>" + "".join(f'<testcase name="{name}" />' for name in REQUIRED_TESTS) + "</testsuite>", encoding="utf-8")


def _reports(directory: Path):
    evaluation, selection, shadow = directory / "evaluation.json", directory / "selection.json", directory / "shadow.json"
    invariants = {name: {"state": "pass", "violations": 0} for name in ("canonical_write", "deterministic", "content_safe", "wrong_project", "cross_project_compare")}
    _write(evaluation, {"report_type": "brain_eleven_authority_evaluation", "suite": "all", "case_count": 180, "expectations_passed": 180, "invariants": invariants})
    _write(selection, {"provider": {"id": "metadata_authority_v1"}, "corpus": {"suite": "all", "task_count": 109}, "metrics": {"wrong_project_leakage_rate": 0}, "invariants": {"wrong_project": {"state": "pass"}}})
    _write(shadow, {"report_type": "brain_eleven_authority_shadow_report", "rollout_mode": "SHADOW", "context_injection": False, "comparison": {"candidate_gate": {"passed": True}, "outcome": "unchanged"}, "authority_policy_invariants": invariants})
    return evaluation, selection, shadow


def test_phase18_manifest_requires_green_metadata_authority_artifacts(tmp_path):
    junit = tmp_path / "results.xml"
    _junit(junit)
    evaluation, selection, shadow = _reports(tmp_path)

    manifest = build_manifest(junit, evaluation, selection, shadow, tmp_path)

    assert manifest["status"] == PASS
    assert manifest["invariants"]["wrong_project_authority_leakage"] == 0


def test_phase18_manifest_refuses_failed_authority_invariant(tmp_path):
    junit = tmp_path / "results.xml"
    _junit(junit)
    evaluation, selection, shadow = _reports(tmp_path)
    document = json.loads(evaluation.read_text(encoding="utf-8"))
    document["invariants"]["wrong_project"]["state"] = "fail"
    _write(evaluation, document)

    with pytest.raises(Phase18EvidenceError, match="hard gates"):
        build_manifest(junit, evaluation, selection, shadow, tmp_path)


def test_phase18_evidence_cli_writes_a_runtime_manifest(tmp_path):
    junit, output = tmp_path / "results.xml", tmp_path / "phase18.json"
    _junit(junit)
    evaluation, selection, shadow = _reports(tmp_path)

    assert main([
        "--junit", str(junit), "--authority-evaluation", str(evaluation), "--selection-evaluation", str(selection),
        "--shadow-report", str(shadow), "--output", str(output), "--root", str(ROOT),
    ]) == 0
    assert json.loads(output.read_text(encoding="utf-8"))["status"] == PASS
