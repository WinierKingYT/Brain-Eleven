#!/usr/bin/env python3
"""Surface bounded, content-safe Trivy OS findings before the hard gate.

The companion workflow still runs a separate SARIF scan with ``exit-code: 1``.
This helper is diagnostic-only: it exposes only CVE/package/version metadata so
maintainers can remediate a failing immutable image without publishing scanner
descriptions, layer paths, image configuration, or application content.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping


MAX_FINDINGS = 20


def _workflow_text(value: object) -> str:
    """Return a bounded, single-line value safe for GitHub annotations."""
    return " ".join(str(value or "unknown").split())[:160].replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def vulnerability_summaries(report: Mapping[str, Any]) -> list[dict[str, str]]:
    """Extract only identity/version fields from a Trivy JSON report."""
    findings: list[dict[str, str]] = []
    for result in report.get("Results", ()):
        if not isinstance(result, Mapping):
            continue
        for vulnerability in result.get("Vulnerabilities", ()):
            if not isinstance(vulnerability, Mapping):
                continue
            finding = {
                "id": _workflow_text(vulnerability.get("VulnerabilityID")),
                "package": _workflow_text(vulnerability.get("PkgName")),
                "installed": _workflow_text(vulnerability.get("InstalledVersion")),
                "fixed": _workflow_text(vulnerability.get("FixedVersion") or "no fixed version"),
            }
            if finding not in findings:
                findings.append(finding)
    return sorted(findings, key=lambda finding: (finding["id"], finding["package"], finding["installed"]))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", required=True, type=Path)
    args = parser.parse_args(argv)

    try:
        document = json.loads(args.report.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        print("::error title=Trivy diagnostics unavailable::The hard security gate must be inspected directly")
        return 0
    if not isinstance(document, Mapping):
        print("::error title=Trivy diagnostics invalid::The hard security gate must be inspected directly")
        return 0

    findings = vulnerability_summaries(document)
    for finding in findings[:MAX_FINDINGS]:
        print(
            "::error title=Trivy OS vulnerability::"
            f"{finding['id']} package={finding['package']} installed={finding['installed']} fixed={finding['fixed']}"
        )
    if len(findings) > MAX_FINDINGS:
        print(f"::error title=Trivy OS vulnerabilities::{len(findings) - MAX_FINDINGS} additional findings omitted")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
