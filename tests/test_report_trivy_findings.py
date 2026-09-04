from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from report_trivy_findings import main, vulnerability_summaries  # noqa: E402


def test_vulnerability_summaries_excludes_untrusted_scanner_descriptions():
    report = {
        "Results": [
            {
                "Vulnerabilities": [
                    {
                        "VulnerabilityID": "CVE-2026-0001",
                        "PkgName": "openssl",
                        "InstalledVersion": "3.0.0",
                        "FixedVersion": "3.0.1",
                        "Title": "API_KEY=must-not-leak",
                        "Description": "untrusted scanner prose",
                    }
                ]
            }
        ]
    }

    assert vulnerability_summaries(report) == [
        {"id": "CVE-2026-0001", "package": "openssl", "installed": "3.0.0", "fixed": "3.0.1"}
    ]


def test_cli_emits_only_safe_trivy_identity_fields(tmp_path, capsys):
    report = tmp_path / "trivy.json"
    report.write_text(
        json.dumps(
            {
                "Results": [
                    {
                        "Vulnerabilities": [
                            {
                                "VulnerabilityID": "CVE-2026-0001",
                                "PkgName": "openssl",
                                "InstalledVersion": "3.0.0",
                                "FixedVersion": "3.0.1",
                                "Description": "SECRET should not appear",
                            }
                        ]
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    assert main(["--report", str(report)]) == 0
    output = capsys.readouterr().out
    assert "CVE-2026-0001 package=openssl installed=3.0.0 fixed=3.0.1" in output
    assert "SECRET" not in output
