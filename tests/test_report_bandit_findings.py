from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from report_bandit_findings import finding_locations, main  # noqa: E402


def test_finding_locations_excludes_source_code_and_rule_prose():
    report = {
        "results": [
            {
                "test_id": "B105",
                "filename": "scripts/example.py",
                "line_number": 12,
                "code": "token = 'must-not-leak'",
                "issue_text": "Hardcoded password string",
            }
        ]
    }

    assert finding_locations(report) == [{"rule": "B105", "path": "scripts/example.py", "line": "12"}]


def test_cli_emits_only_safe_bandit_location_data(tmp_path, capsys):
    report = tmp_path / "bandit.json"
    report.write_text(
        json.dumps(
            {
                "results": [
                    {
                        "test_id": "B105",
                        "filename": "scripts/example.py",
                        "line_number": 12,
                        "code": "SECRET",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    assert main(["--report", str(report)]) == 0
    output = capsys.readouterr().out
    assert "B105 at scripts/example.py:12" in output
    assert "SECRET" not in output
