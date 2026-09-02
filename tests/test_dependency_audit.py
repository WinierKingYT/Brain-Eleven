"""Tests for truthful dependency-audit outcome classification."""

import importlib.util
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
SPEC = importlib.util.spec_from_file_location("dependency_audit", SCRIPTS / "dependency_audit.py")
dependency_audit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(dependency_audit)


def test_classify_result_pass_requires_zero_exit_and_zero_vulnerabilities():
    payload = {"dependencies": [{"name": "safe", "vulns": []}]}
    assert dependency_audit.classify_result(0, payload)["status"] == dependency_audit.PASS


def test_classify_result_vulnerability_is_not_hidden_by_nonzero_exit():
    payload = {"dependencies": [{"name": "unsafe", "vulns": [{"id": "PYSEC-1"}]}]}
    result = dependency_audit.classify_result(1, payload)
    assert result["status"] == dependency_audit.VULNERABILITY_FOUND
    assert result["vulnerability_count"] == 1


def test_classify_result_nonzero_without_a_valid_report_is_scanner_error():
    result = dependency_audit.classify_result(2, None, "network unavailable")
    assert result["status"] == dependency_audit.SCANNER_ERROR
    assert result["vulnerability_count"] is None
