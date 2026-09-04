#!/usr/bin/env python3
"""Bind Phase 15–19 evidence to one tested Context Engine Foundation revision."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess  # nosec B404 - fixed no-shell Git metadata command only.
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from defusedxml import ElementTree


PASS = "PASS"
FAIL = "FAIL"
PHASE_FILES = {"15": "phase15", "16": "phase16", "17": "phase17", "18": "phase18", "19": "phase19"}
REQUIRED_GRADUATION_TESTS = frozenset(
    {
        "test_fifty_concurrent_state_writers_persist_every_success_without_lost_updates",
        "test_one_hundred_contested_state_transactions_preserve_every_success",
        "test_full_pipeline_is_deterministic_across_one_hundred_identical_runs",
    }
)


class FoundationEvidenceError(RuntimeError):
    """Raised when artifacts cannot substantiate a foundation freeze claim."""


def _load_json(path: Path, label: str) -> Mapping[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise FoundationEvidenceError(f"Cannot parse {label}: {path}") from exc
    if not isinstance(value, Mapping):
        raise FoundationEvidenceError(f"{label} must be a JSON object")
    return value


def _git_sha(root: Path) -> str:
    try:
        result = subprocess.run(  # nosec B603
            [shutil.which("git") or "git", "rev-parse", "HEAD"],
            cwd=root,
            text=True,
            capture_output=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise FoundationEvidenceError("Cannot resolve the current Git revision") from exc
    sha = result.stdout.strip()
    if not sha:
        raise FoundationEvidenceError("Current Git revision is empty")
    return sha


def _test_results(path: Path) -> dict[str, str]:
    try:
        root = ElementTree.parse(path).getroot()
    except (OSError, ElementTree.ParseError) as exc:
        raise FoundationEvidenceError(f"Cannot parse graduation JUnit evidence: {path}") from exc
    result = {
        str(case.get("name") or "").split("[", 1)[0]: (
            FAIL if case.find("failure") is not None or case.find("error") is not None else PASS
        )
        for case in root.iter("testcase")
    }
    if not result:
        raise FoundationEvidenceError("Graduation JUnit evidence contains no test cases")
    return result


def _phase_manifest(path: Path, phase: str, sha: str) -> Mapping[str, Any]:
    manifest = _load_json(path, f"Phase {phase} evidence")
    if manifest.get("phase") != phase or manifest.get("status") != PASS:
        raise FoundationEvidenceError(f"Phase {phase} evidence is not a passing manifest")
    if manifest.get("head_sha") != sha:
        raise FoundationEvidenceError(f"Phase {phase} evidence is not bound to the current revision")
    invariants = manifest.get("invariants")
    if not isinstance(invariants, Mapping):
        raise FoundationEvidenceError(f"Phase {phase} evidence has no invariant section")
    return {"head_sha": sha, "invariants": dict(invariants), "status": PASS}


def _zero(invariants: Mapping[str, Any], key: str, phase: str) -> int:
    value = invariants.get(key)
    if value != 0:
        raise FoundationEvidenceError(f"Phase {phase} invariant {key} is not proven as zero")
    return 0


def build_manifest(
    *,
    junit: Path,
    phase_paths: Mapping[str, Path],
    root: Path = Path("."),
) -> Mapping[str, Any]:
    """Return a derived manifest; never execute source code or edit evidence."""
    sha = _git_sha(root)
    if set(phase_paths) != set(PHASE_FILES):
        raise FoundationEvidenceError("Exactly Phase 15–19 evidence paths are required")
    phase_results = {phase: _phase_manifest(path, phase, sha) for phase, path in phase_paths.items()}
    tests = _test_results(junit)
    missing = sorted(REQUIRED_GRADUATION_TESTS - tests.keys())
    failed = sorted(name for name in REQUIRED_GRADUATION_TESTS if tests.get(name) == FAIL)
    if missing or failed:
        raise FoundationEvidenceError("Graduation JUnit evidence is missing a required passing test")

    phase16, phase17, phase18, phase19 = (phase_results[phase]["invariants"] for phase in ("16", "17", "18", "19"))
    hard_invariants = {
        "wrong_project_leakage": _zero(phase16, "wrong_project_state_leakage", "16"),
        "lost_updates": _zero(phase16, "lost_state_updates", "16"),
        "canonical_write_from_router": _zero(phase17, "canonical_write", "17"),
        "canonical_write_from_authority": _zero(phase18, "canonical_write", "18"),
        "canonical_write_from_compiler": _zero(phase19, "canonical_write", "19"),
        "forbidden_context": _zero(phase15 := phase_results["15"]["invariants"], "forbidden_context", "15"),
        "nondeterminism": _zero(phase19, "nondeterminism", "19"),
    }
    return {
        "schema_version": 1,
        "foundation": "context-engine-v1",
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "git_sha": sha,
        "status": PASS,
        "phases": {phase: result["status"] for phase, result in sorted(phase_results.items())},
        "phase_evidence": phase_results,
        "graduation_tests": {"required": sorted(REQUIRED_GRADUATION_TESTS), "passed": sorted(REQUIRED_GRADUATION_TESTS)},
        "hard_invariants": hard_invariants,
        "runtime": {"phase17": "SHADOW", "phase18": "SHADOW", "phase19": "SHADOW"},
        "review_status": "PENDING_INDEPENDENT_REVIEW",
    }


def _atomic_write(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Create Context Engine Foundation V1 evidence from CI artifacts")
    parser.add_argument("--junit", type=Path, required=True)
    for phase, argument in PHASE_FILES.items():
        parser.add_argument(f"--{argument}", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--root", type=Path, default=Path("."))
    args = parser.parse_args(argv)
    paths = {phase: getattr(args, argument) for phase, argument in PHASE_FILES.items()}
    try:
        manifest = build_manifest(junit=args.junit, phase_paths=paths, root=args.root)
        _atomic_write(args.output, manifest)
    except FoundationEvidenceError as exc:
        print(json.dumps({"status": FAIL, "error": str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps({"status": PASS, "output": str(args.output)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
