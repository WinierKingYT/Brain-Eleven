"""IG01-E independent audit probes; no production provider is executed."""

from __future__ import annotations

import copy
from pathlib import Path

import pytest

from evals.ig01e.audit import AuditError, audit_repository, write_audit_report


ROOT = Path(__file__).resolve().parents[1]


def test_audit_is_revision_bound_and_content_free():
    report = audit_repository(ROOT)
    assert report["source"]["git_sha"] == __import__("subprocess").run(
        ["git", "-C", str(ROOT), "rev-parse", "HEAD"], capture_output=True, text=True, check=True
    ).stdout.strip()
    # The repository is expected to be clean in CI.  During local development
    # this candidate is deliberately FIX-FIRST until it is committed.
    assert report["verdict"] == "FIX-FIRST"  # no CI pair artifact was supplied
    assert report["phase20"] == "FROZEN_LOCKED"
    assert report["v2_runtime"] == "SHADOW"
    assert report["checks"]["benchmark_eligibility"]["evidence"]["eligibility"] == "EXPLORATORY_ONLY" if report["checks"]["benchmark_eligibility"]["status"] == "PASS" else True
    serialized = str(report).lower()
    assert "prompt" not in serialized
    assert "transcript" not in serialized
    assert "memory_content" not in serialized


def test_audit_report_write_is_content_free(tmp_path):
    report = audit_repository(ROOT)
    path = tmp_path / "ig01e-audit.json"
    write_audit_report(path, report)
    assert path.is_file()
    assert "prompt" not in path.read_text(encoding="utf-8").lower()


def test_audit_rejects_missing_contract_marker(tmp_path):
    # The audit must fail closed if a required contract is unavailable.
    for source in ("IG01-EVALUATION-FOUNDATION.md", "IG01-A-EVALUATION-CONTRACT.md"):
        target = tmp_path / source
        target.write_text("incomplete", encoding="utf-8")
    with pytest.raises(AuditError):
        from evals.ig01e.audit import _check_file
        _check_file(tmp_path, "IG01-EVALUATION-FOUNDATION.md", required_markers=("IG01-E",))


def test_audit_report_writer_rejects_unknown_verdict(tmp_path):
    with pytest.raises(AuditError):
        write_audit_report(tmp_path / "bad.json", {"audit_version": "1.0.0", "verdict": "PASS"})


def test_audit_report_writer_rejects_failed_ship(tmp_path):
    report = audit_repository(ROOT)
    report = copy.deepcopy(report)
    report["verdict"] = "SHIP"
    report["checks"]["revision_clean"] = {"status": "FAIL", "error_code": "DIRTY"}
    with pytest.raises(AuditError, match="failed check"):
        write_audit_report(tmp_path / "bad.json", report)


def test_audit_report_writer_rejects_malformed_check(tmp_path):
    report = audit_repository(ROOT)
    report = copy.deepcopy(report)
    report["checks"]["revision_clean"] = None
    with pytest.raises(AuditError, match="checks are malformed"):
        write_audit_report(tmp_path / "bad.json", report)
