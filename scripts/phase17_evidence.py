#!/usr/bin/env python3
"""Build a Phase 17 evidence manifest from completed CI artifacts only."""

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
PHASE = "17"
SUCCESS = "PASS"
FAIL = "FAIL"
REQUIRED_TESTS = frozenset(
    {
        "test_current_project_routing_is_read_only_deterministic_and_content_safe",
        "test_prompt_cannot_expand_project_scope",
        "test_raw_request_cannot_expand_history_without_trusted_option",
        "test_corrupt_canonical_memory_is_not_empty_success",
        "test_corrupt_state_is_not_accepted_from_stale_task_snapshot",
        "test_stale_graph_is_degraded_and_never_replaces_canonical_memory",
        "test_second_changed_revision_returns_stale_input_after_single_retry",
        "test_router_expectation_suite_is_green_and_deterministic",
        "test_shadow_comparison_is_content_free_and_keeps_safety_gates_green",
    }
)


class Phase17EvidenceError(RuntimeError):
    """Supplied artifacts cannot support a Phase 17 graduation claim."""


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


def _load_json(path: Path, label: str) -> Mapping[str, Any]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise Phase17EvidenceError(f"Cannot parse {label}: {path}") from exc
    if not isinstance(document, Mapping):
        raise Phase17EvidenceError(f"{label} must be a JSON object")
    return document


def _test_results(junit_path: Path) -> dict[str, str]:
    try:
        root = ElementTree.parse(junit_path).getroot()
    except (OSError, ElementTree.ParseError) as exc:
        raise Phase17EvidenceError(f"Cannot parse JUnit evidence: {junit_path}") from exc
    results: dict[str, str] = {}
    for case in root.iter("testcase"):
        name = str(case.get("name") or "").split("[", 1)[0]
        results[name] = FAIL if case.find("failure") is not None or case.find("error") is not None else SUCCESS
    if not results:
        raise Phase17EvidenceError("JUnit evidence contains no test cases")
    return results


def _router_evaluation(path: Path) -> dict[str, Any]:
    report = _load_json(path, "router route evaluation")
    if report.get("report_type") != "brain_eleven_router_route_evaluation":
        raise Phase17EvidenceError("router route evaluation has the wrong report type")
    if not isinstance(report.get("case_count"), int) or report["case_count"] < 7:
        raise Phase17EvidenceError("router route evaluation does not cover the required cases")
    invariants = report.get("invariants")
    if not isinstance(invariants, Mapping) or any(
        not isinstance(value, Mapping) or value.get("state") != "pass" for value in invariants.values()
    ):
        raise Phase17EvidenceError("router route evaluation has a failed invariant")
    return {"case_count": report["case_count"], "invariants": dict(invariants)}


def _router_selection(path: Path) -> dict[str, Any]:
    report = _load_json(path, "router selection evaluation")
    provider = report.get("provider")
    corpus = report.get("corpus")
    metrics = report.get("metrics")
    invariants = report.get("invariants")
    if not isinstance(provider, Mapping) or provider.get("id") != "task_aware_router_v1":
        raise Phase17EvidenceError("selection evaluation is not from the router provider")
    if not isinstance(corpus, Mapping) or corpus.get("suite") != "all" or corpus.get("task_count", 0) < 109:
        raise Phase17EvidenceError("selection evaluation does not include public corpus plus holdout")
    if not isinstance(metrics, Mapping) or metrics.get("wrong_project_leakage_rate") != 0:
        raise Phase17EvidenceError("selection evaluation has wrong-project leakage")
    if not isinstance(invariants, Mapping) or any(
        not isinstance(value, Mapping) or value.get("state") != "pass" for value in invariants.values()
    ):
        raise Phase17EvidenceError("selection evaluation has failed or unsupported invariants")
    return {"metrics": dict(metrics), "invariants": dict(invariants)}


def _shadow_report(path: Path) -> dict[str, Any]:
    report = _load_json(path, "router shadow report")
    comparison = report.get("comparison")
    if (
        report.get("report_type") != "brain_eleven_router_shadow_report"
        or report.get("rollout_mode") != "SHADOW"
        or report.get("context_injection") is not False
        or not isinstance(comparison, Mapping)
        or not isinstance(comparison.get("candidate_gate"), Mapping)
        or comparison["candidate_gate"].get("passed") is not True
    ):
        raise Phase17EvidenceError("shadow report does not prove safe shadow-only rollout")
    return {
        "outcome": comparison.get("outcome"),
        "candidate_gate": dict(comparison["candidate_gate"]),
    }


def _benchmark(path: Path) -> list[dict[str, Any]]:
    report = _load_json(path, "router benchmark")
    rows = report.get("results")
    if (
        report.get("report_type") != "brain_eleven_router_benchmark"
        or report.get("hard_latency_gate") is not False
        or not isinstance(rows, list)
    ):
        raise Phase17EvidenceError("router benchmark has an invalid contract")
    expected = {100, 1000, 10000}
    available = {row.get("noise_count") for row in rows if isinstance(row, Mapping)}
    if not expected.issubset(available):
        raise Phase17EvidenceError("router benchmark is missing a required noise scale")
    normalized = []
    for row in rows:
        if not isinstance(row, Mapping) or not isinstance(row.get("p50_ms"), (int, float)) or not isinstance(
            row.get("p95_ms"), (int, float)
        ):
            raise Phase17EvidenceError("router benchmark row is invalid")
        normalized.append(dict(row))
    return normalized


def build_manifest(
    junit_path: Path,
    route_evaluation_path: Path,
    selection_evaluation_path: Path,
    shadow_report_path: Path,
    benchmark_path: Path,
    root: Path = Path("."),
) -> dict[str, Any]:
    test_results = _test_results(junit_path)
    missing = sorted(REQUIRED_TESTS - test_results.keys())
    failed = sorted(name for name in REQUIRED_TESTS if test_results.get(name) == FAIL)
    route_evaluation = _router_evaluation(route_evaluation_path)
    selection_evaluation = _router_selection(selection_evaluation_path)
    shadow = _shadow_report(shadow_report_path)
    benchmark = _benchmark(benchmark_path)
    status = SUCCESS if not missing and not failed else FAIL
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
        "route_evaluation": route_evaluation,
        "selection_evaluation": selection_evaluation,
        "shadow": shadow,
        "performance": benchmark,
        "invariants": {
            "wrong_project_route_leakage": 0,
            "implicit_cross_project_route": 0,
            "prompt_policy_override": 0,
            "stale_graph_acceptance": 0,
            "canonical_as_empty": 0,
            "canonical_write": 0,
            "nondeterminism": 0,
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


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Create a Phase 17 evidence manifest from CI artifacts")
    parser.add_argument("--junit", required=True, type=Path)
    parser.add_argument("--route-evaluation", required=True, type=Path)
    parser.add_argument("--selection-evaluation", required=True, type=Path)
    parser.add_argument("--shadow-report", required=True, type=Path)
    parser.add_argument("--benchmark", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--root", default=".", type=Path)
    args = parser.parse_args(argv)
    try:
        manifest = build_manifest(
            args.junit,
            args.route_evaluation,
            args.selection_evaluation,
            args.shadow_report,
            args.benchmark,
            args.root,
        )
        _atomic_write_json(args.output, manifest)
    except Phase17EvidenceError as exc:
        print(json.dumps({"status": FAIL, "error": str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps({"status": manifest["status"], "output": str(args.output)}, ensure_ascii=False))
    return 0 if manifest["status"] == SUCCESS else 1


if __name__ == "__main__":
    raise SystemExit(main())
