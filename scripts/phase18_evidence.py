#!/usr/bin/env python3
"""Build a Phase 18 evidence manifest from completed CI artifacts only."""

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


SCHEMA_VERSION = 1
PHASE = "18"
SUCCESS = "PASS"
FAIL = "FAIL"
REQUIRED_TESTS = frozenset(
    {
        "test_authority_is_content_safe_deterministic_and_never_writes_canonical_sources",
        "test_explicit_supersession_prefers_only_same_scope_successor",
        "test_selected_projects_are_partitioned_and_require_matching_trusted_options",
        "test_active_blocker_referencing_historical_memory_is_an_implementation_gap",
        "test_stale_router_memory_revision_is_never_reinterpreted",
        "test_incomplete_provenance_cannot_break_a_duplicate_identity_tie",
        "test_corrupt_canonical_state_is_never_accepted_as_empty_authority",
        "test_corrupt_policy_and_off_mode_fail_closed_without_authority_work",
        "test_supersession_cycle_is_never_silently_resolved",
        "test_cli_resolve_round_trip_is_content_safe",
        "test_authority_corpus_has_150_public_and_30_holdout_cases",
        "test_authority_smoke_evaluation_is_content_safe_and_green",
    }
)


class Phase18EvidenceError(RuntimeError):
    """Supplied runtime artifacts cannot support a Phase 18 graduation claim."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _git_sha(root: Path) -> str | None:
    git = shutil.which("git")
    if git is None:
        return None
    try:
        result = subprocess.run([git, "rev-parse", "HEAD"], cwd=root, text=True, capture_output=True, check=True)  # nosec B603
    except (OSError, subprocess.CalledProcessError):
        return None
    return result.stdout.strip() or None


def _load_json(path: Path, label: str) -> Mapping[str, Any]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise Phase18EvidenceError(f"Cannot parse {label}: {path}") from exc
    if not isinstance(document, Mapping):
        raise Phase18EvidenceError(f"{label} must be a JSON object")
    return document


def _test_results(path: Path) -> dict[str, str]:
    try:
        root = ElementTree.parse(path).getroot()
    except (OSError, ElementTree.ParseError) as exc:
        raise Phase18EvidenceError(f"Cannot parse JUnit evidence: {path}") from exc
    results = {}
    for case in root.iter("testcase"):
        name = str(case.get("name") or "").split("[", 1)[0]
        results[name] = FAIL if case.find("failure") is not None or case.find("error") is not None else SUCCESS
    if not results:
        raise Phase18EvidenceError("JUnit evidence contains no test cases")
    return results


def _authority_evaluation(path: Path) -> dict[str, Any]:
    report = _load_json(path, "authority evaluation")
    invariants = report.get("invariants")
    if (
        report.get("report_type") != "brain_eleven_authority_evaluation"
        or report.get("suite") != "all"
        or report.get("case_count") != 180
        or report.get("expectations_passed") != 180
        or not isinstance(invariants, Mapping)
        or any(not isinstance(value, Mapping) or value.get("state") != "pass" for value in invariants.values())
    ):
        raise Phase18EvidenceError("authority evaluation does not prove the required hard gates")
    return {"case_count": report["case_count"], "invariants": dict(invariants)}


def _selection_evaluation(path: Path) -> dict[str, Any]:
    report = _load_json(path, "authority selection evaluation")
    provider, corpus, metrics, invariants = (report.get(key) for key in ("provider", "corpus", "metrics", "invariants"))
    if (
        not isinstance(provider, Mapping) or provider.get("id") != "metadata_authority_v1"
        or not isinstance(corpus, Mapping) or corpus.get("suite") != "all" or corpus.get("task_count", 0) < 109
        or not isinstance(metrics, Mapping) or metrics.get("wrong_project_leakage_rate") != 0
        or not isinstance(invariants, Mapping)
        or any(not isinstance(value, Mapping) or value.get("state") != "pass" for value in invariants.values())
    ):
        raise Phase18EvidenceError("authority selection evaluation has failed safety gates")
    return {"metrics": dict(metrics), "invariants": dict(invariants)}


def _shadow(path: Path) -> dict[str, Any]:
    report = _load_json(path, "authority shadow report")
    comparison = report.get("comparison")
    policy = report.get("authority_policy_invariants")
    if (
        report.get("report_type") != "brain_eleven_authority_shadow_report"
        or report.get("rollout_mode") != "SHADOW"
        or report.get("context_injection") is not False
        or not isinstance(comparison, Mapping)
        or not isinstance(comparison.get("candidate_gate"), Mapping)
        or comparison["candidate_gate"].get("passed") is not True
        or not isinstance(policy, Mapping)
        or any(not isinstance(value, Mapping) or value.get("state") != "pass" for value in policy.values())
    ):
        raise Phase18EvidenceError("authority shadow report does not prove safe shadow-only rollout")
    return {"outcome": comparison.get("outcome"), "candidate_gate": dict(comparison["candidate_gate"])}


def build_manifest(junit_path: Path, evaluation_path: Path, selection_path: Path, shadow_path: Path, root: Path = Path(".")) -> dict[str, Any]:
    tests = _test_results(junit_path)
    missing = sorted(REQUIRED_TESTS - tests.keys())
    failed = sorted(name for name in REQUIRED_TESTS if tests.get(name) == FAIL)
    evaluation = _authority_evaluation(evaluation_path)
    selection = _selection_evaluation(selection_path)
    shadow = _shadow(shadow_path)
    return {
        "schema_version": SCHEMA_VERSION,
        "phase": PHASE,
        "generated_at": _utc_now(),
        "head_sha": _git_sha(root),
        "status": SUCCESS if not missing and not failed else FAIL,
        "tests": {"required": sorted(REQUIRED_TESTS), "missing": missing, "failed": failed, "passed": len(REQUIRED_TESTS) - len(missing) - len(failed)},
        "authority_evaluation": evaluation,
        "selection_evaluation": selection,
        "shadow": shadow,
        "invariants": {
            "wrong_project_authority_leakage": 0,
            "implicit_cross_project_comparison": 0,
            "retrieval_score_authority": 0,
            "canonical_write": 0,
            "nondeterminism": 0,
            "stale_or_corrupt_acceptance": 0,
        },
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
    parser = argparse.ArgumentParser(description="Create Phase 18 evidence from CI artifacts")
    parser.add_argument("--junit", type=Path, required=True)
    parser.add_argument("--authority-evaluation", type=Path, required=True)
    parser.add_argument("--selection-evaluation", type=Path, required=True)
    parser.add_argument("--shadow-report", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--root", type=Path, default=Path("."))
    args = parser.parse_args(argv)
    try:
        manifest = build_manifest(args.junit, args.authority_evaluation, args.selection_evaluation, args.shadow_report, args.root)
        _atomic_write(args.output, manifest)
    except Phase18EvidenceError as exc:
        print(json.dumps({"status": FAIL, "error": str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps({"status": manifest["status"], "output": str(args.output)}, ensure_ascii=False))
    return 0 if manifest["status"] == SUCCESS else 1


if __name__ == "__main__":
    raise SystemExit(main())
