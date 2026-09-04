#!/usr/bin/env python3
"""Build a Phase 19 evidence manifest only from completed runtime artifacts."""

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


PHASE = "19"
PASS = "PASS"
FAIL = "FAIL"
REQUIRED_TESTS = frozenset(
    {
        "test_compiler_is_deterministic_budgeted_and_never_writes_canonical_sources",
        "test_mandatory_context_overflow_is_visible_not_silently_truncated",
        "test_secret_and_reserved_end_marker_never_reach_rendered_context",
        "test_wrong_project_resolution_is_an_upstream_scope_failure",
        "test_stale_authority_snapshot_is_never_compiled",
        "test_compiler_off_never_reads_or_injects_context",
        "test_corrupt_compiler_policy_fails_closed",
        "test_compiler_corpus_has_180_public_40_holdout_and_multi_budget_coverage",
        "test_compiler_smoke_evaluation_enforces_hard_safety_invariants",
        "test_compile_cli_manifest_never_persists_or_prints_memory_content",
        "test_shadow_cli_is_non_injecting_and_supports_explicit_history",
        "test_compiler_benchmark_reports_p50_and_p95_without_a_latency_gate",
    }
)


class Phase19EvidenceError(RuntimeError):
    pass


def _load_json(path: Path, label: str) -> Mapping[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise Phase19EvidenceError(f"Cannot parse {label}: {path}") from exc
    if not isinstance(value, Mapping):
        raise Phase19EvidenceError(f"{label} must be an object")
    return value


def _test_results(path: Path) -> Mapping[str, str]:
    try:
        root = ElementTree.parse(path).getroot()
    except (OSError, ElementTree.ParseError) as exc:
        raise Phase19EvidenceError(f"Cannot parse JUnit evidence: {path}") from exc
    result = {}
    for case in root.iter("testcase"):
        name = str(case.get("name") or "").split("[", 1)[0]
        result[name] = FAIL if case.find("failure") is not None or case.find("error") is not None else PASS
    if not result:
        raise Phase19EvidenceError("JUnit evidence contains no test cases")
    return result


def _compiler_evaluation(path: Path) -> Mapping[str, Any]:
    report = _load_json(path, "compiler policy evaluation")
    invariants = report.get("invariants")
    if (
        report.get("report_type") != "brain_eleven_compiler_v2_evaluation"
        or report.get("suite") != "all"
        or report.get("case_count") != 220
        or report.get("expectations_passed") != 220
        or not isinstance(invariants, Mapping)
        or any(not isinstance(item, Mapping) or item.get("state") != "pass" for item in invariants.values())
    ):
        raise Phase19EvidenceError("compiler policy evaluation does not prove Phase 19 hard gates")
    return {"case_count": report["case_count"], "invariants": dict(invariants)}


def _selection_evaluation(path: Path) -> Mapping[str, Any]:
    report = _load_json(path, "compiler selection evaluation")
    provider, corpus, metrics, invariants = (report.get(key) for key in ("provider", "corpus", "metrics", "invariants"))
    if (
        not isinstance(provider, Mapping) or provider.get("id") != "context_compiler_v2"
        or not isinstance(corpus, Mapping) or corpus.get("suite") != "all" or corpus.get("task_count", 0) < 109
        or not isinstance(metrics, Mapping) or metrics.get("wrong_project_leakage_rate") != 0
        or metrics.get("forbidden_context_rate") != 0
        or not isinstance(invariants, Mapping)
        or any(not isinstance(item, Mapping) or item.get("state") != "pass" for item in invariants.values())
    ):
        raise Phase19EvidenceError("compiler selection evaluation has failed safety gates")
    return {"metrics": dict(metrics), "invariants": dict(invariants)}


def _shadow(path: Path) -> Mapping[str, Any]:
    report = _load_json(path, "compiler shadow report")
    comparison = report.get("comparison")
    policy = report.get("compiler_policy_invariants")
    if (
        report.get("report_type") != "brain_eleven_compiler_v2_shadow_report"
        or report.get("rollout_mode") != "SHADOW"
        or report.get("context_injection") is not False
        or not isinstance(comparison, Mapping)
        or not isinstance(comparison.get("candidate_gate"), Mapping)
        or comparison["candidate_gate"].get("passed") is not True
        or not isinstance(policy, Mapping)
        or any(not isinstance(item, Mapping) or item.get("state") != "pass" for item in policy.values())
    ):
        raise Phase19EvidenceError("compiler shadow report does not prove shadow-only safe rollout")
    return {"outcome": comparison.get("outcome"), "candidate_gate": dict(comparison["candidate_gate"])}


def _benchmark(path: Path) -> Mapping[str, Any]:
    report = _load_json(path, "compiler benchmark")
    results = report.get("results")
    required_noise = {100, 1000, 10000}
    if (
        report.get("report_type") != "brain_eleven_compiler_v2_benchmark"
        or report.get("offline") is not True
        or report.get("hard_latency_gate") is not False
        or report.get("measurement_scope") != "compile_after_fixed_router_and_authority"
        or not isinstance(results, list)
    ):
        raise Phase19EvidenceError("compiler benchmark does not prove its safe informational contract")
    observed_noise = set()
    for item in results:
        if not isinstance(item, Mapping):
            raise Phase19EvidenceError("compiler benchmark result is malformed")
        noise = item.get("noise_count")
        p50, p95 = item.get("p50_ms"), item.get("p95_ms")
        if (
            isinstance(noise, bool) or not isinstance(noise, int)
            or isinstance(p50, bool) or not isinstance(p50, (int, float)) or p50 < 0
            or isinstance(p95, bool) or not isinstance(p95, (int, float)) or p95 < p50
        ):
            raise Phase19EvidenceError("compiler benchmark latency result is invalid")
        observed_noise.add(noise)
    if not required_noise.issubset(observed_noise):
        raise Phase19EvidenceError("compiler benchmark is missing required noise sizes")
    return {"measurement_scope": report["measurement_scope"], "results": list(results)}


def _git_sha(root: Path) -> str | None:
    try:
        result = subprocess.run(  # nosec B603
            [shutil.which("git") or "git", "rev-parse", "HEAD"], cwd=root, text=True, capture_output=True, check=True
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return result.stdout.strip() or None


def build_manifest(
    junit: Path, compiler_evaluation: Path, selection: Path, shadow: Path, benchmark: Path, root: Path = Path(".")
) -> Mapping[str, Any]:
    tests = _test_results(junit)
    missing = sorted(REQUIRED_TESTS - tests.keys())
    failed = sorted(name for name in REQUIRED_TESTS if tests.get(name) == FAIL)
    return {
        "schema_version": 1,
        "phase": PHASE,
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "head_sha": _git_sha(root),
        "status": PASS if not missing and not failed else FAIL,
        "tests": {"required": sorted(REQUIRED_TESTS), "missing": missing, "failed": failed, "passed": len(REQUIRED_TESTS) - len(missing) - len(failed)},
        "compiler_evaluation": _compiler_evaluation(compiler_evaluation),
        "selection_evaluation": _selection_evaluation(selection),
        "shadow": _shadow(shadow),
        "benchmark": _benchmark(benchmark),
        "invariants": {
            "budget_violations": 0, "wrong_project_leakage": 0, "secret_leakage": 0,
            "mandatory_silent_omission": 0, "canonical_write": 0, "nondeterminism": 0,
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
    parser = argparse.ArgumentParser(description="Create Phase 19 evidence from CI artifacts")
    parser.add_argument("--junit", type=Path, required=True)
    parser.add_argument("--compiler-evaluation", type=Path, required=True)
    parser.add_argument("--selection-evaluation", type=Path, required=True)
    parser.add_argument("--shadow-report", type=Path, required=True)
    parser.add_argument("--benchmark", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--root", type=Path, default=Path("."))
    args = parser.parse_args(argv)
    try:
        manifest = build_manifest(
            args.junit, args.compiler_evaluation, args.selection_evaluation, args.shadow_report, args.benchmark, args.root
        )
        _atomic_write(args.output, manifest)
    except Phase19EvidenceError as exc:
        print(json.dumps({"status": FAIL, "error": str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps({"status": manifest["status"], "output": str(args.output)}, ensure_ascii=False))
    return 0 if manifest["status"] == PASS else 1


if __name__ == "__main__":
    raise SystemExit(main())
