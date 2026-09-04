from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from report_junit_failures import failed_cases, main  # noqa: E402


def test_failed_cases_extracts_bounded_safe_failure_data(tmp_path):
    report = tmp_path / "results.xml"
    report.write_text(
        """<?xml version=\"1.0\"?>
        <testsuite><testcase classname=\"tests.sample\" name=\"test_failure\">
        <failure>expected % value
        next line</failure>
        </testcase><testcase classname=\"tests.sample\" name=\"test_ok\" /></testsuite>""",
        encoding="utf-8",
    )

    cases = failed_cases(report)
    assert cases == ["tests.sample.test_failure"]


def test_cli_reports_readable_failure_as_a_workflow_annotation(tmp_path, capsys):
    report = tmp_path / "results.xml"
    report.write_text(
        "<testsuite><testcase classname=\"tests.sample\" name=\"test_failure\"><error>bad</error></testcase></testsuite>",
        encoding="utf-8",
    )

    assert main(["--junit", str(report)]) == 1
    output = capsys.readouterr().out
    assert "::error title=Unit test failed::tests.sample.test_failure" in output
    assert "bad" not in output
