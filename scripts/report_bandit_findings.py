#!/usr/bin/env python3
"""Print bounded, source-safe Bandit diagnostics before its hard gate.

This command intentionally returns success because the following workflow step
is the authoritative Bandit hard gate. It reveals only rule IDs, repository
paths, and line numbers; it never prints source lines or user-controlled data.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping


MAX_FINDINGS = 20


def _safe_text(value: object) -> str:
    return " ".join(str(value or "unknown").split())[:160].replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def finding_locations(report: Mapping[str, Any]) -> list[dict[str, str]]:
    """Extract a deterministic, content-free location for each Bandit rule."""
    findings: list[dict[str, str]] = []
    for result in report.get("results", ()):
        if not isinstance(result, Mapping):
            continue
        finding = {
            "rule": _safe_text(result.get("test_id")),
            "path": _safe_text(result.get("filename")),
            "line": _safe_text(result.get("line_number")),
        }
        if finding not in findings:
            findings.append(finding)
    return sorted(findings, key=lambda finding: (finding["path"], finding["line"], finding["rule"]))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        document = json.loads(args.report.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        print("::error title=Bandit diagnostics unavailable::The following hard security gate must be inspected directly")
        return 0
    if not isinstance(document, Mapping):
        print("::error title=Bandit diagnostics invalid::The following hard security gate must be inspected directly")
        return 0
    findings = finding_locations(document)
    for finding in findings[:MAX_FINDINGS]:
        print(
            "::error title=Bandit security finding::"
            f"{finding['rule']} at {finding['path']}:{finding['line']}"
        )
    if len(findings) > MAX_FINDINGS:
        print(f"::error title=Bandit security findings::{len(findings) - MAX_FINDINGS} additional findings omitted")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
