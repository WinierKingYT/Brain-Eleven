#!/usr/bin/env python3
"""Generate evidence-backed Phase 14G graduation manifests.

The manifest is a runtime artifact, never a hand-maintained status claim. It
derives test and coverage facts from JUnit/Cobertura output. CI may mark its
security dependency gate as PASS only after every hard security job succeeds.
Live Docker Compose verification remains intentionally independent.
"""

import argparse
import json
import os
import platform
import shutil
import subprocess  # nosec B404
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from defusedxml import ElementTree as element_tree

PHASE = "14G"
SCHEMA_VERSION = 1
MINIMUM_COVERAGE = 80.0
# Evidence status, never a credential.
PASS = "PASS"  # nosec B105
FAIL = "FAIL"
NOT_VERIFIED = "NOT_VERIFIED"
PARTIALLY_VERIFIED = "PARTIALLY_VERIFIED"

INVARIANT_CASES = {
    "canonical_integrity": (
        "test_invalid_canonical_input_hard_fails_without_becoming_empty",
        "test_invalid_mutation_and_tempfile_permission_error_preserve_canonical",
    ),
    "concurrent_writes": (
        "test_ten_parallel_writers_and_twenty_reopened_transactions_have_no_lost_updates",
        "test_lock_timeout_is_explicit_and_crashed_writer_releases_the_os_lock",
    ),
    "project_isolation": (
        "test_disaster_drill_rebuilds_context_without_cross_project_leakage",
        "test_context_compiler_retrieves_global_and_current_project_only",
    ),
    "stale_projection_safety": (
        "test_missing_or_corrupt_derived_state_is_rebuilt_and_stale_or_foreign_context_is_rejected",
        "test_saved_bootstrap_is_rejected_after_canonical_revision_changes",
    ),
    "backup_restore": (
        "test_restore_preserves_identity_then_rebuilds_derived_state",
        "test_tampered_or_unmanifested_archive_is_refused",
    ),
    "migration_recovery": (
        "test_interrupted_migration_preserves_canonical_then_reruns_and_rolls_back",
    ),
    "hook_truthfulness": (
        "test_step_never_treats_an_existing_stale_artifact_as_success",
        "test_pipeline_marks_validator_failure_as_failed",
    ),
}


class GraduationEvidenceError(RuntimeError):
    """Raised when runtime output cannot support a trustworthy manifest."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _git_sha(root: Path) -> Optional[str]:
    git = shutil.which("git")
    if not git:
        return None
    try:
        # This is a fixed, shell-free Git query; ``git`` is resolved to an absolute path.
        completed = subprocess.run(  # nosec B603
            [git, "rev-parse", "HEAD"],
            cwd=root,
            text=True,
            capture_output=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return completed.stdout.strip() or None


def _case_status(case) -> str:
    if case.find("failure") is not None or case.find("error") is not None:
        return FAIL
    if case.find("skipped") is not None:
        return NOT_VERIFIED
    return PASS


def _parse_junit(path: Path) -> Dict:
    try:
        root = element_tree.parse(path).getroot()
    except (OSError, element_tree.ParseError) as exc:
        raise GraduationEvidenceError(f"Cannot parse JUnit evidence: {path}") from exc

    cases = []
    for case in root.iter("testcase"):
        name = str(case.get("name") or "").split("[", 1)[0]
        cases.append({"name": name, "status": _case_status(case)})
    if not cases:
        raise GraduationEvidenceError("JUnit evidence contains no test cases")

    failed = sum(case["status"] == FAIL for case in cases)
    skipped = sum(case["status"] == NOT_VERIFIED for case in cases)
    return {
        "status": PASS if not failed else FAIL,
        "total": len(cases),
        "passed": len(cases) - failed - skipped,
        "failed": failed,
        "skipped": skipped,
        "cases": cases,
    }


def _parse_coverage(path: Path) -> Dict:
    try:
        root = element_tree.parse(path).getroot()
        line_rate = float(root.attrib["line-rate"])
    except (OSError, KeyError, ValueError, element_tree.ParseError) as exc:
        raise GraduationEvidenceError(f"Cannot parse coverage evidence: {path}") from exc
    percent = round(line_rate * 100, 2)
    return {
        "status": PASS if percent >= MINIMUM_COVERAGE else FAIL,
        "percent": percent,
        "minimum": MINIMUM_COVERAGE,
    }


def _invariants(cases: List[Dict]) -> Dict:
    by_name = {}
    for case in cases:
        by_name.setdefault(case["name"], []).append(case["status"])

    output = {}
    for name, expected_cases in INVARIANT_CASES.items():
        statuses = [
            status
            for case_name in expected_cases
            for status in by_name.get(case_name, [])
        ]
        if len(statuses) < len(expected_cases):
            output[name] = {"status": NOT_VERIFIED, "missing_cases": list(expected_cases)}
        elif all(status == PASS for status in statuses):
            output[name] = {"status": PASS, "cases": list(expected_cases)}
        else:
            output[name] = {"status": FAIL, "cases": list(expected_cases)}
    return output


def build_manifest(
    junit_path: Path,
    coverage_path: Path,
    security_status: str = NOT_VERIFIED,
    root: Path = Path("."),
) -> Dict:
    """Build a manifest exclusively from supplied runtime evidence files."""
    if security_status not in {PASS, NOT_VERIFIED}:
        raise GraduationEvidenceError("security_status must be PASS or NOT_VERIFIED")
    tests = _parse_junit(junit_path)
    coverage = _parse_coverage(coverage_path)
    invariants = _invariants(tests["cases"])
    invariant_statuses = {item["status"] for item in invariants.values()}
    if FAIL in invariant_statuses or tests["status"] == FAIL or coverage["status"] == FAIL:
        overall = FAIL
    elif NOT_VERIFIED in invariant_statuses or security_status != PASS:
        overall = PARTIALLY_VERIFIED
    else:
        overall = PASS

    return {
        "schema_version": SCHEMA_VERSION,
        "phase": PHASE,
        "generated_at": _utc_now(),
        "head_sha": _git_sha(root),
        "runtime": {
            "python": platform.python_version(),
            "platform": platform.platform(),
        },
        "tests": {key: value for key, value in tests.items() if key != "cases"},
        "coverage": coverage,
        "security": {
            "status": security_status,
            "source": "Validation security dependency gate" if security_status == PASS else None,
        },
        "invariants": invariants,
        "metrics": {
            "wrong_project_leakage": 0 if invariants["project_isolation"]["status"] == PASS else None,
            "lost_updates": 0 if invariants["concurrent_writes"]["status"] == PASS else None,
        },
        "deployment": {
            "status": NOT_VERIFIED,
            "reason": "Live Docker Compose runtime verification is an explicit separate check.",
        },
        "status": overall,
    }


def _atomic_write_json(path: Path, document: Dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(document, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink()


def collect(
    junit_path: Path,
    coverage_path: Path,
    output_path: Path,
    security_status: str = NOT_VERIFIED,
    root: Path = Path("."),
) -> Dict:
    manifest = build_manifest(junit_path, coverage_path, security_status, root)
    _atomic_write_json(output_path, manifest)
    return manifest


def run_local_evidence(output_path: Path, root: Path, python: str) -> Dict:
    """Run the full offline test/coverage command, then collect its evidence."""
    with tempfile.TemporaryDirectory(prefix="brain-eleven-evidence-") as temporary:
        temporary_root = Path(temporary)
        junit_path = temporary_root / "pytest-results.xml"
        coverage_path = temporary_root / "coverage.xml"
        coverage_data = temporary_root / ".coverage"
        environment = {**os.environ, "COVERAGE_FILE": str(coverage_data)}
        command = [
            python,
            "-m",
            "pytest",
            "tests/",
            "-q",
            f"--junitxml={junit_path}",
            "--cov=scripts",
            f"--cov-report=xml:{coverage_path}",
            "--cov-report=",
            "--cov-fail-under=80",
        ]
        # The command has fixed offline pytest arguments; only its interpreter is configurable.
        completed = subprocess.run(  # nosec B603
            command, cwd=root, env=environment, check=False
        )
        if completed.returncode:
            raise GraduationEvidenceError(
                f"Graduation evidence test command failed with exit code {completed.returncode}"
            )
        return collect(junit_path, coverage_path, output_path, NOT_VERIFIED, root)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Generate Phase 14G runtime evidence")
    commands = parser.add_subparsers(dest="command", required=True)

    collect_parser = commands.add_parser("collect", help="Collect manifest from JUnit and coverage files")
    collect_parser.add_argument("--junit", required=True)
    collect_parser.add_argument("--coverage", required=True)
    collect_parser.add_argument("--output", required=True)
    collect_parser.add_argument("--security-status", choices=(PASS, NOT_VERIFIED), default=NOT_VERIFIED)
    collect_parser.add_argument("--root", default=".")

    run_parser = commands.add_parser("run", help="Run the full offline evidence command")
    run_parser.add_argument("--output", required=True)
    run_parser.add_argument("--root", default=".")
    run_parser.add_argument("--python", default=sys.executable)

    args = parser.parse_args(argv)
    try:
        if args.command == "collect":
            manifest = collect(
                Path(args.junit),
                Path(args.coverage),
                Path(args.output),
                args.security_status,
                Path(args.root),
            )
        else:
            manifest = run_local_evidence(Path(args.output), Path(args.root), args.python)
    except GraduationEvidenceError as exc:
        print(json.dumps({"status": FAIL, "error": str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps({"status": manifest["status"], "output": str(args.output)}, ensure_ascii=False))
    return 0 if manifest["status"] != FAIL else 1


if __name__ == "__main__":
    raise SystemExit(main())
