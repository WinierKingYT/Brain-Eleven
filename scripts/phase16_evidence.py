#!/usr/bin/env python3
"""Create Phase 16 evidence only from completed test and evaluation artifacts."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess  # nosec B404 - fixed local Git metadata command only.
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from defusedxml import ElementTree


SCHEMA_VERSION = 1
PHASE = "16"
PASS = "PASS"
FAIL = "FAIL"
REQUIRED_TESTS = frozenset({
    "test_ten_concurrent_state_writers_persist_every_success_without_lost_updates",
    "test_corrupt_state_and_unsupported_schema_fail_closed",
    "test_lock_timeout_and_write_failure_leave_the_previous_canonical_snapshot_intact",
    "test_ai_proposed_state_and_invalid_memory_references_cannot_become_canonical",
    "test_bootstrap_includes_current_state_and_rejects_a_changed_state_revision",
    "test_corrupt_current_state_is_never_injected_as_empty_bootstrap",
    "test_backup_restore_preserves_canonical_project_state_when_present",
})


class Phase16EvidenceError(RuntimeError):
    """Raised when supplied evidence cannot support a Phase 16 claim."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _git_sha(root: Path) -> str | None:
    git = shutil.which("git")
    if git is None:
        return None
    try:
        result = subprocess.run(  # nosec B603 - fixed no-shell Git invocation.
            [git, "rev-parse", "HEAD"], cwd=root, text=True, capture_output=True, check=True
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return result.stdout.strip() or None


def _test_results(junit_path: Path) -> dict[str, str]:
    try:
        root = ElementTree.parse(junit_path).getroot()
    except (OSError, ElementTree.ParseError) as exc:
        raise Phase16EvidenceError(f"Cannot parse JUnit evidence: {junit_path}") from exc
    results: dict[str, str] = {}
    for case in root.iter("testcase"):
        name = str(case.get("name") or "").split("[", 1)[0]
        status = FAIL if case.find("failure") is not None or case.find("error") is not None else PASS
        results[name] = status
    if not results:
        raise Phase16EvidenceError("JUnit evidence contains no test cases")
    return results


def _evaluation_report(path: Path) -> dict[str, Any]:
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise Phase16EvidenceError(f"Cannot parse evaluation evidence: {path}") from exc
    if not isinstance(report, Mapping):
        raise Phase16EvidenceError("Evaluation evidence must be a JSON object")
    if report.get("provider") != "task_state_v1" or report.get("suite") != "all":
        raise Phase16EvidenceError("Evaluation evidence is not the Phase 16 full suite")
    metrics = report.get("metrics")
    invariants = report.get("invariants")
    if not isinstance(metrics, Mapping) or not isinstance(invariants, Mapping):
        raise Phase16EvidenceError("Evaluation evidence has no metrics or invariants")
    if metrics.get("task_case_count", 0) < 28 or metrics.get("state_case_count", 0) < 28:
        raise Phase16EvidenceError("Evaluation evidence does not cover the required public and holdout cases")
    if any(not isinstance(value, Mapping) or value.get("state") != "pass" for value in invariants.values()):
        raise Phase16EvidenceError("Evaluation evidence contains a failed hard invariant")
    if metrics.get("wrong_project_state_leakage_rate") != 0:
        raise Phase16EvidenceError("Evaluation evidence contains non-zero wrong-project state leakage")
    return {"metrics": dict(metrics), "invariants": dict(invariants)}


def build_manifest(junit_path: Path, evaluation_path: Path, root: Path = Path(".")) -> dict[str, Any]:
    """Build an evidence manifest without executing tests or evaluating source code."""
    test_results = _test_results(junit_path)
    missing = sorted(REQUIRED_TESTS - test_results.keys())
    failed = sorted(
        name for name in REQUIRED_TESTS if name in test_results and test_results[name] != PASS
    )
    evaluation = _evaluation_report(evaluation_path)
    status = PASS if not missing and not failed else FAIL
    return {
        "schema_version": SCHEMA_VERSION,
        "phase": PHASE,
        "generated_at": _utc_now(),
        "head_sha": _git_sha(root),
        "status": status,
        "tests": {
            "required": sorted(REQUIRED_TESTS),
            "missing": missing,
            "failed": failed,
            "passed": len(REQUIRED_TESTS) - len(missing) - len(failed),
        },
        "task_state_evaluation": evaluation,
        "invariants": {
            "wrong_project_state_leakage": 0
            if evaluation["metrics"]["wrong_project_state_leakage_rate"] == 0 else None,
            "lost_state_updates": 0 if not failed else None,
            "corrupt_state_fail_closed": PASS
            if "test_corrupt_state_and_unsupported_schema_fail_closed" not in failed else FAIL,
            "bootstrap_state_lineage": PASS
            if "test_bootstrap_includes_current_state_and_rejects_a_changed_state_revision" not in failed else FAIL,
        },
    }


def _atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink()


def collect(junit_path: Path, evaluation_path: Path, output_path: Path, root: Path = Path(".")) -> dict[str, Any]:
    manifest = build_manifest(junit_path, evaluation_path, root)
    _atomic_write_json(output_path, manifest)
    return manifest


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Create a Phase 16 evidence manifest from runtime artifacts")
    parser.add_argument("--junit", required=True)
    parser.add_argument("--evaluation", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--root", default=".")
    arguments = parser.parse_args(argv)
    try:
        manifest = collect(
            Path(arguments.junit), Path(arguments.evaluation), Path(arguments.output), Path(arguments.root)
        )
    except Phase16EvidenceError as exc:
        print(json.dumps({"status": FAIL, "error": str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps({"status": manifest["status"], "output": str(arguments.output)}, ensure_ascii=False))
    return 0 if manifest["status"] == PASS else 1


if __name__ == "__main__":
    raise SystemExit(main())
