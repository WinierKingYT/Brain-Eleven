"""W-09 status, privacy and legacy-boundary evidence tests."""

from __future__ import annotations

import copy
from pathlib import Path

import pytest

from evals.baseline_snapshot import DEFAULT_BASELINE_PATH
from evals.metrics import CaseEvaluation, CaseMetrics
from evals.reporting import EvaluationReportError, read_evaluation_report
from evals.run import run_evaluation
from evals.ig01c.engine import reconcile_report, source_fingerprint_for_root


ROOT = Path(__file__).resolve().parents[1]
CORPUS_ROOT = ROOT / "evals" / "corpus"


def _metrics() -> CaseMetrics:
    return CaseMetrics(
        task_id="task-1",
        selected_count=0,
        relevant_selected_count=0,
        required_count=1,
        required_selected_count=0,
        useful_selected_count=0,
        context_precision=0.0,
        context_recall=0.0,
        wrong_project_selected_count=0,
        wrong_project_leakage_count=0,
        forbidden_context_count=0,
        superseded_selected_count=0,
        superseded_leakage_count=0,
        resolved_selected_count=0,
        resolved_leakage_count=0,
        unlabeled_selection_count=0,
    )


def test_unsupported_case_is_not_a_pass():
    evaluation = CaseEvaluation(
        metrics=_metrics(),
        invariants={"scope_isolation": "unsupported"},
        selected_ids=(),
    )

    assert evaluation.passed is False
    assert evaluation.violations == ()
    assert evaluation.unsupported_invariants == ("scope_isolation",)
    assert evaluation.as_dict()["unsupported_invariants"] == ["scope_isolation"]


def test_generic_report_is_measurement_only_and_provider_unavailable_for_evidence():
    report = run_evaluation(suite="smoke", corpus_root=CORPUS_ROOT)

    assert report["evaluation_status"]["safety"]["state"] == "pass"
    assert report["evaluation_status"]["quality"]["state"] == "measured"
    assert report["evaluation_status"]["evidence"]["state"] == "unavailable"
    assert report["evaluation_status"]["measurement"] == "incomplete"
    assert report["evaluation_status"]["promotion"] == "blocked"


def test_generic_report_rejects_unknown_nested_fields_and_raw_content():
    report = run_evaluation(suite="smoke", corpus_root=CORPUS_ROOT)

    unknown = copy.deepcopy(report)
    unknown["cases"][0]["unexpected"] = 1
    with pytest.raises(EvaluationReportError):
        read_evaluation_report(_write_json(tmp_path=None, report=unknown))

    raw = copy.deepcopy(report)
    raw["cases"][0]["prompt"] = "private prompt"
    with pytest.raises(EvaluationReportError):
        read_evaluation_report(_write_json(tmp_path=None, report=raw))


def _write_json(*, tmp_path, report):
    # Keep this helper local so test fixtures never touch committed evidence.
    import tempfile
    import json

    directory = Path(tmp_path) if tmp_path is not None else Path(tempfile.mkdtemp(prefix="w09-report-"))
    path = directory / "report.json"
    path.write_text(json.dumps(report), encoding="utf-8")
    return path


def test_existing_schema_one_baseline_is_explicitly_legacy():
    report = read_evaluation_report(DEFAULT_BASELINE_PATH)

    assert report["schema_version"] == 1
    assert report["evaluation_status"]["evidence"]["state"] == "legacy"
    assert report["evaluation_status"]["promotion"] == "blocked"


def test_ig01c_reconciliation_requires_root_and_detects_false_fingerprint():
    from evals.ig01c.engine import evaluate_corpus

    case = {
        "case_id": "retrieval-1",
        "family": "retrieval",
        "candidate_ids": ["required"],
        "required_ids": ["required"],
        "acceptable_ids": [],
        "forbidden_ids": [],
        "project_id": "project-a",
        "candidate_metadata": [{"id": "required", "project_id": "project-a"}],
    }
    report = evaluate_corpus(
        [case], {"retrieval-1": {"retrieved_ids": ["required"]}},
        corpus_version="ig-eval-v2", split="dev", enforce_benchmark=False,
        source_root=ROOT,
    )
    assert report["evaluation_status"]["evidence"]["state"] == "verified"
    assert reconcile_report(report, ROOT)["evaluation_status"]["evidence"]["state"] == "verified"

    tampered = copy.deepcopy(report)
    tampered["source"]["source_fingerprint"] = "sha256:" + "f" * 64
    # The report remains structurally valid but its declared digest cannot be
    # reconciled with the frozen three-file allowlist.
    reconciled = reconcile_report(tampered, ROOT)
    assert reconciled["evaluation_status"]["evidence"]["state"] == "tampered"

    unbound = reconcile_report(report, None)
    assert unbound["evaluation_status"]["evidence"]["state"] == "unavailable"
    assert source_fingerprint_for_root(ROOT).startswith("sha256:")
