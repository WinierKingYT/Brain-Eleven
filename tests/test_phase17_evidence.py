"""Tests for truthful Phase 17 evidence construction."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from phase17_evidence import PASS, Phase17EvidenceError, REQUIRED_TESTS, build_manifest  # noqa: E402


def _write_junit(path: Path) -> None:
    cases = "".join(f'<testcase name="{name}" />' for name in sorted(REQUIRED_TESTS))
    path.write_text(f"<testsuite>{cases}</testsuite>", encoding="utf-8")


def _write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value), encoding="utf-8")


def _write_required_reports(directory: Path, *, leakage: float = 0.0) -> tuple[Path, Path, Path, Path]:
    route = directory / "route.json"
    selection = directory / "selection.json"
    shadow = directory / "shadow.json"
    benchmark = directory / "benchmark.json"
    _write_json(
        route,
        {
            "report_type": "brain_eleven_router_route_evaluation",
            "case_count": 7,
            "invariants": {"wrong_project_leakage": {"state": "pass"}},
        },
    )
    _write_json(
        selection,
        {
            "provider": {"id": "task_aware_router_v1"},
            "corpus": {"suite": "all", "task_count": 109},
            "metrics": {"wrong_project_leakage_rate": leakage},
            "invariants": {"wrong_project_leakage": {"state": "pass"}},
        },
    )
    _write_json(
        shadow,
        {
            "report_type": "brain_eleven_router_shadow_report",
            "rollout_mode": "SHADOW",
            "context_injection": False,
            "comparison": {"candidate_gate": {"passed": True}, "outcome": "unchanged"},
        },
    )
    _write_json(
        benchmark,
        {
            "report_type": "brain_eleven_router_benchmark",
            "hard_latency_gate": False,
            "results": [
                {"noise_count": size, "p50_ms": 1.0, "p95_ms": 2.0}
                for size in (100, 1000, 10000)
            ],
        },
    )
    return route, selection, shadow, benchmark


def test_phase17_manifest_requires_green_router_artifacts(tmp_path):
    junit = tmp_path / "results.xml"
    _write_junit(junit)
    route, selection, shadow, benchmark = _write_required_reports(tmp_path)

    manifest = build_manifest(junit, route, selection, shadow, benchmark, tmp_path)

    assert manifest["status"] == PASS
    assert manifest["invariants"]["wrong_project_route_leakage"] == 0


def test_phase17_manifest_refuses_router_leakage(tmp_path):
    junit = tmp_path / "results.xml"
    _write_junit(junit)
    route, selection, shadow, benchmark = _write_required_reports(tmp_path, leakage=0.1)

    with pytest.raises(Phase17EvidenceError, match="wrong-project leakage"):
        build_manifest(junit, route, selection, shadow, benchmark, tmp_path)
