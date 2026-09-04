"""Offline evaluation suites must remain deterministic and CI-sized."""

from __future__ import annotations

from pathlib import Path

from evals.reporting import read_evaluation_report
from evals.run import _gate_failed, main, run_evaluation, suite_task_paths


ROOT = Path(__file__).resolve().parents[1]
CORPUS_ROOT = ROOT / "evals" / "corpus"


def test_suite_boundaries_match_the_committed_corpus_split():
    assert len(suite_task_paths(CORPUS_ROOT, "smoke")) == 47
    assert len(suite_task_paths(CORPUS_ROOT, "public")) == 101
    assert len(suite_task_paths(CORPUS_ROOT, "holdout")) == 8
    assert len(suite_task_paths(CORPUS_ROOT, "all")) == 109


def test_smoke_runner_is_deterministic_and_safety_clean():
    first = run_evaluation(suite="smoke", corpus_root=CORPUS_ROOT)
    second = run_evaluation(suite="smoke", corpus_root=CORPUS_ROOT)

    assert first == second
    assert first["metrics"]["case_count"] == 47
    assert all(summary["state"] == "pass" for summary in first["invariants"].values())


def test_unsupported_safety_invariant_fails_the_cli_gate():
    report = {"invariants": {"wrong_project_leakage": {"state": "unsupported"}}}

    assert _gate_failed(report) is True


def test_cli_writes_a_machine_readable_smoke_report(tmp_path):
    output = tmp_path / "smoke-report.json"

    assert main(["--suite", "smoke", "--report", str(output)]) == 0

    report = read_evaluation_report(output)
    assert report["corpus"]["suite"] == "smoke"
    assert report["metrics"]["case_count"] == 47
