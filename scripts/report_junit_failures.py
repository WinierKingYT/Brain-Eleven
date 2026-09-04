#!/usr/bin/env python3
"""Surface failed pytest cases as concise GitHub Actions annotations.

The workflow keeps the unit-test gate hard: pytest is allowed to finish only
so its JUnit report can name the failed cases, and this command then exits
non-zero. The report is deliberately content-free and bounded so test payloads
cannot leak through workflow annotations or alter CI control flow.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from defusedxml import ElementTree


MAX_FAILURES = 10
def _escape_workflow_message(value: str) -> str:
    """Return one safe, single-line GitHub workflow-command message."""
    return (
        " ".join(value.split())
        .replace("%", "%25")
        .replace("\r", "%0D")
        .replace("\n", "%0A")
    )


def failed_cases(junit_path: Path) -> list[str]:
    """Extract failed/error test identities without exposing test payloads."""
    try:
        root = ElementTree.parse(junit_path).getroot()
    except (OSError, ElementTree.ParseError):
        return ["JUnit evidence unavailable"]

    failures: list[str] = []
    for case in root.iter("testcase"):
        issue = case.find("failure")
        if issue is None:
            issue = case.find("error")
        if issue is None:
            continue
        identity = ".".join(part for part in (case.get("classname"), case.get("name")) if part)
        failures.append(identity or "unnamed test")
    return failures


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--junit", required=True, type=Path)
    args = parser.parse_args(argv)

    failures = failed_cases(args.junit)
    if not failures:
        print("::error title=Unit test failure::pytest failed without a readable JUnit failure record")
        return 1

    for identity in failures[:MAX_FAILURES]:
        print(
            "::error title=Unit test failed::"
            f"{_escape_workflow_message(identity)} — inspect the protected JUnit artifact for diagnostics"
        )
    if len(failures) > MAX_FAILURES:
        print(f"::error title=Unit test failures::{len(failures) - MAX_FAILURES} additional failures omitted")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
