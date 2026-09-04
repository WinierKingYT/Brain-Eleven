"""Truthfulness checks for Phase 15 generated graduation evidence."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from phase15_evidence import PASS, Phase15EvidenceError, REQUIRED_TESTS, build_manifest, main  # noqa: E402


def _write(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value), encoding="utf-8")


def _junit(path: Path) -> None:
    cases = "".join(f'<testcase name="{name}" />' for name in sorted(REQUIRED_TESTS))
    path.write_text(f"<testsuite>{cases}</testsuite>", encoding="utf-8")


def _report(case_count: int, suite: str, source: dict | None = None) -> dict:
    invariants = {
        name: {"state": "pass", "failed_case_ids": []}
        for name in ("forbidden_context", "resolved_lifecycle_leakage", "superseded_lifecycle_leakage", "wrong_project_leakage")
    }
    report = {
        "provider": {"id": "context_compiler_baseline_v1"},
        "corpus": {"suite": suite, "task_count": case_count},
        "metrics": {
            "case_count": case_count,
            "wrong_project_leakage_rate": 0,
            "forbidden_context_rate": 0,
        },
        "invariants": invariants,
    }
    if source is not None:
        report["source"] = source
    return report


def test_phase15_manifest_requires_immutable_baseline_and_full_corpus(tmp_path):
    junit, baseline, evaluation = tmp_path / "tests.xml", tmp_path / "baseline.json", tmp_path / "all.json"
    _junit(junit)
    _write(baseline, _report(130, "public", {"baseline_id": "baseline-v2"}))
    _write(evaluation, _report(160, "all"))

    manifest = build_manifest(junit, baseline, evaluation, tmp_path)

    assert manifest["status"] == PASS
    assert manifest["baseline_v2"]["source"]["baseline_id"] == "baseline-v2"


def test_phase15_manifest_refuses_a_non_zero_scope_leakage(tmp_path):
    junit, baseline, evaluation = tmp_path / "tests.xml", tmp_path / "baseline.json", tmp_path / "all.json"
    _junit(junit)
    _write(baseline, _report(130, "public", {"baseline_id": "baseline-v2"}))
    invalid = _report(160, "all")
    invalid["metrics"]["wrong_project_leakage_rate"] = 1
    _write(evaluation, invalid)

    with pytest.raises(Phase15EvidenceError, match="hard gates"):
        build_manifest(junit, baseline, evaluation, tmp_path)


def test_phase15_evidence_cli_atomically_writes_a_content_free_manifest(tmp_path, capsys):
    junit, baseline, evaluation, output = (
        tmp_path / "tests.xml",
        tmp_path / "baseline.json",
        tmp_path / "all.json",
        tmp_path / "phase15.json",
    )
    _junit(junit)
    _write(baseline, _report(130, "public", {"baseline_id": "baseline-v2"}))
    _write(evaluation, _report(160, "all"))

    assert main(["--junit", str(junit), "--baseline", str(baseline), "--evaluation", str(evaluation), "--output", str(output), "--root", str(ROOT)]) == 0

    assert json.loads(output.read_text(encoding="utf-8"))["status"] == PASS
    assert "private memory" not in capsys.readouterr().out
