#!/usr/bin/env python3
"""Fail closed when context-engine packages hide behind legacy coverage."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping, Sequence


GLOBAL_MINIMUM = 80.0
CORE_MINIMUM = 85.0
CORE_GROUPS = {
    "context_router": ("context_router/",),
    "authority": ("authority/",),
    "context_compiler_v2": ("context_compiler_v2/",),
    "retrieval_decision_v2": ("retrieval_decision_v2/",),
    "task_state": (
        "scripts/task_model.py", "scripts/task_state_context.py", "scripts/state_store.py",
        "scripts/state_resolver.py", "scripts/state.py",
    ),
}


class CoverageGateError(ValueError):
    """Coverage input cannot prove the required production thresholds."""


def _summary(file_data: Mapping[str, Any]) -> tuple[int, int]:
    summary = file_data.get("summary")
    if not isinstance(summary, Mapping):
        raise CoverageGateError("coverage file entry is missing a summary")
    statements = summary.get("num_statements")
    covered = summary.get("covered_lines")
    if not isinstance(statements, int) or not isinstance(covered, int) or statements < 1 or covered < 0:
        raise CoverageGateError("coverage file entry has invalid line totals")
    return statements, covered


def _matches(filename: str, paths: tuple[str, ...]) -> bool:
    normalized = filename.replace("\\", "/")
    return any(normalized == path or normalized.endswith("/" + path) or normalized.startswith(path) for path in paths)


def evaluate_coverage(document: Mapping[str, Any]) -> dict[str, Any]:
    files = document.get("files")
    totals = document.get("totals")
    if not isinstance(files, Mapping) or not isinstance(totals, Mapping):
        raise CoverageGateError("coverage JSON has an unsupported schema")
    total_percent = totals.get("percent_covered")
    if not isinstance(total_percent, (int, float)):
        raise CoverageGateError("coverage JSON is missing the global percentage")
    groups: dict[str, dict[str, Any]] = {}
    failures: list[str] = []
    if float(total_percent) < GLOBAL_MINIMUM:
        failures.append(f"global={float(total_percent):.2f}<{GLOBAL_MINIMUM:.2f}")
    for name, paths in CORE_GROUPS.items():
        matched = [(filename, data) for filename, data in files.items() if isinstance(data, Mapping) and _matches(str(filename), paths)]
        if not matched:
            failures.append(f"{name}=missing")
            groups[name] = {"files": 0, "percent": 0.0}
            continue
        statements, covered = 0, 0
        for _filename, data in matched:
            file_statements, file_covered = _summary(data)
            statements += file_statements
            covered += file_covered
        percent = (covered / statements) * 100
        groups[name] = {"files": len(matched), "statements": statements, "covered": covered, "percent": percent}
        if percent < CORE_MINIMUM:
            failures.append(f"{name}={percent:.2f}<{CORE_MINIMUM:.2f}")
    return {
        "schema_version": 1,
        "global_percent": float(total_percent),
        "groups": groups,
        "failures": failures,
        "status": "pass" if not failures else "fail",
    }


def check_coverage(path: Path | str) -> dict[str, Any]:
    try:
        document = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CoverageGateError(f"cannot parse coverage JSON: {path}") from exc
    if not isinstance(document, Mapping):
        raise CoverageGateError("coverage JSON root must be an object")
    return evaluate_coverage(document)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Enforce coverage for every context-engine production package.")
    parser.add_argument("--coverage", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = check_coverage(args.coverage)
    except CoverageGateError as exc:
        parser.error(str(exc))
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
