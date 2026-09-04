"""Truthfulness checks for Phase 19 generated graduation evidence."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from phase19_evidence import PASS, Phase19EvidenceError, REQUIRED_TESTS, build_manifest, main  # noqa: E402


def _write(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value), encoding="utf-8")


def _reports(directory: Path) -> tuple[Path, Path, Path, Path]:
    policy, selection, shadow, benchmark = (
        directory / "policy.json", directory / "selection.json", directory / "shadow.json", directory / "benchmark.json"
    )
    invariants = {
        name: {"state": "pass", "violations": 0}
        for name in ("budget", "canonical_write", "deterministic", "mandatory_silent_omission", "secret_leakage", "wrong_project")
    }
    _write(policy, {"report_type": "brain_eleven_compiler_v2_evaluation", "suite": "all", "case_count": 220, "expectations_passed": 220, "invariants": invariants})
    _write(selection, {
        "provider": {"id": "context_compiler_v2"}, "corpus": {"suite": "all", "task_count": 109},
        "metrics": {"wrong_project_leakage_rate": 0, "forbidden_context_rate": 0},
        "invariants": {"wrong_project_leakage": {"state": "pass"}},
    })
    _write(shadow, {
        "report_type": "brain_eleven_compiler_v2_shadow_report", "rollout_mode": "SHADOW", "context_injection": False,
        "comparison": {"candidate_gate": {"passed": True}, "outcome": "degraded"},
        "compiler_policy_invariants": invariants,
    })
    _write(benchmark, {
        "report_type": "brain_eleven_compiler_v2_benchmark", "offline": True, "hard_latency_gate": False,
        "measurement_scope": "compile_after_fixed_router_and_authority",
        "results": [{"noise_count": size, "p50_ms": 1.0, "p95_ms": 2.0} for size in (100, 1000, 10000)],
    })
    return policy, selection, shadow, benchmark


def _junit(path: Path) -> None:
    cases = "".join(f'<testcase name="{name}" />' for name in sorted(REQUIRED_TESTS))
    path.write_text(f"<testsuite>{cases}</testsuite>", encoding="utf-8")


def test_phase19_manifest_requires_green_budget_and_shadow_artifacts(tmp_path):
    junit = tmp_path / "results.xml"
    _junit(junit)
    policy, selection, shadow, benchmark = _reports(tmp_path)

    manifest = build_manifest(junit, policy, selection, shadow, benchmark, tmp_path)

    assert manifest["status"] == PASS
    assert manifest["invariants"]["mandatory_silent_omission"] == 0


def test_phase19_manifest_refuses_forbidden_context_leakage(tmp_path):
    junit = tmp_path / "results.xml"
    _junit(junit)
    policy, selection, shadow, benchmark = _reports(tmp_path)
    value = json.loads(selection.read_text(encoding="utf-8"))
    value["metrics"]["forbidden_context_rate"] = 0.1
    _write(selection, value)

    with pytest.raises(Phase19EvidenceError, match="safety gates"):
        build_manifest(junit, policy, selection, shadow, benchmark, tmp_path)


def test_phase19_evidence_cli_writes_a_runtime_manifest(tmp_path):
    junit, output = tmp_path / "results.xml", tmp_path / "phase19.json"
    _junit(junit)
    policy, selection, shadow, benchmark = _reports(tmp_path)

    assert main([
        "--junit", str(junit), "--compiler-evaluation", str(policy), "--selection-evaluation", str(selection),
        "--shadow-report", str(shadow), "--benchmark", str(benchmark), "--output", str(output), "--root", str(ROOT),
    ]) == 0
    assert json.loads(output.read_text(encoding="utf-8"))["status"] == PASS
