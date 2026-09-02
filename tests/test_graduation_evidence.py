"""Tests for evidence manifests derived from runtime test outputs."""

import sys
import xml.etree.ElementTree as element_tree
from pathlib import Path

import pytest


SCRIPTS = Path(__file__).parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

import graduation_evidence as evidence  # noqa: E402


def _write_junit(path: Path, failed_case: str = "") -> None:
    root = element_tree.Element("testsuite")
    for cases in evidence.INVARIANT_CASES.values():
        for name in cases:
            case = element_tree.SubElement(root, "testcase", name=name, classname="graduation")
            if name == failed_case:
                element_tree.SubElement(case, "failure", message="simulated failure")
    element_tree.ElementTree(root).write(path, encoding="utf-8", xml_declaration=True)


def _write_coverage(path: Path, line_rate: str = "0.835") -> None:
    path.write_text(f'<coverage line-rate="{line_rate}"/>', encoding="utf-8")


def test_collect_derives_passed_metrics_from_runtime_xml(tmp_path, monkeypatch):
    junit = tmp_path / "junit.xml"
    coverage = tmp_path / "coverage.xml"
    output = tmp_path / "phase14-graduation.json"
    _write_junit(junit)
    _write_coverage(coverage)
    monkeypatch.setattr(evidence, "_git_sha", lambda _root: "abc123")

    manifest = evidence.collect(junit, coverage, output, evidence.PASS, tmp_path)

    assert manifest["status"] == evidence.PASS
    assert manifest["tests"] == {"status": evidence.PASS, "total": 13, "passed": 13, "failed": 0, "skipped": 0}
    assert manifest["coverage"] == {"status": evidence.PASS, "percent": 83.5, "minimum": 80.0}
    assert manifest["metrics"] == {"wrong_project_leakage": 0, "lost_updates": 0}
    assert manifest["security"]["status"] == evidence.PASS
    assert manifest["deployment"]["status"] == evidence.NOT_VERIFIED
    assert output.exists()


def test_collect_marks_failed_invariant_and_coverage_without_hiding_it(tmp_path):
    junit = tmp_path / "junit.xml"
    coverage = tmp_path / "coverage.xml"
    _write_junit(junit, "test_ten_parallel_writers_and_twenty_reopened_transactions_have_no_lost_updates")
    _write_coverage(coverage, "0.799")

    manifest = evidence.build_manifest(junit, coverage, evidence.PASS, tmp_path)

    assert manifest["status"] == evidence.FAIL
    assert manifest["coverage"]["status"] == evidence.FAIL
    assert manifest["invariants"]["concurrent_writes"]["status"] == evidence.FAIL
    assert manifest["metrics"]["lost_updates"] is None


def test_collect_refuses_missing_or_malformed_runtime_evidence(tmp_path):
    coverage = tmp_path / "coverage.xml"
    _write_coverage(coverage)

    with pytest.raises(evidence.GraduationEvidenceError, match="Cannot parse JUnit"):
        evidence.build_manifest(tmp_path / "missing.xml", coverage, root=tmp_path)

    junit = tmp_path / "junit.xml"
    _write_junit(junit)
    (tmp_path / "bad-coverage.xml").write_text("not xml", encoding="utf-8")
    with pytest.raises(evidence.GraduationEvidenceError, match="Cannot parse coverage"):
        evidence.build_manifest(junit, tmp_path / "bad-coverage.xml", root=tmp_path)
