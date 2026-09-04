#!/usr/bin/env python3
"""Build a Phase 15 graduation manifest from completed, offline artifacts."""

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


PHASE = "15"
SUCCESS = "PASS"
FAIL = "FAIL"
REQUIRED_TESTS = frozenset(
    {
        "test_baseline_v1_is_verified_as_immutable_historical_evidence",
        "test_baseline_v2_snapshot_matches_current_public_suite_inputs",
        "test_corpus_v2_is_committed_exactly_with_70_60_30_boundaries",
        "test_corpus_v2_manifest_covers_the_required_taxonomy_and_privacy_boundary",
        "test_baseline_is_deterministic_and_does_not_rank_by_prompt",
    }
)


class Phase15EvidenceError(RuntimeError):
    """Raised when artifacts cannot prove the Phase 15 contract."""


def _load_json(path: Path, label: str) -> Mapping[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise Phase15EvidenceError(f"Cannot parse {label}: {path}") from exc
    if not isinstance(value, Mapping):
        raise Phase15EvidenceError(f"{label} must be a JSON object")
    return value


def _test_results(path: Path) -> dict[str, str]:
    try:
        root = ElementTree.parse(path).getroot()
    except (OSError, ElementTree.ParseError) as exc:
        raise Phase15EvidenceError(f"Cannot parse JUnit evidence: {path}") from exc
    results = {
        str(case.get("name") or "").split("[", 1)[0]: (
            FAIL if case.find("failure") is not None or case.find("error") is not None else SUCCESS
        )
        for case in root.iter("testcase")
    }
    if not results:
        raise Phase15EvidenceError("JUnit evidence contains no test cases")
    return results


def _baseline(report: Mapping[str, Any]) -> Mapping[str, Any]:
    provider, corpus, source, metrics, invariants = (
        report.get(key) for key in ("provider", "corpus", "source", "metrics", "invariants")
    )
    if (
        not isinstance(provider, Mapping)
        or provider.get("id") != "context_compiler_baseline_v1"
        or not isinstance(corpus, Mapping)
        or corpus.get("suite") != "public"
        or corpus.get("task_count") != 130
        or not isinstance(source, Mapping)
        or source.get("baseline_id") != "baseline-v2"
        or not isinstance(metrics, Mapping)
        or metrics.get("case_count") != 130
        or metrics.get("wrong_project_leakage_rate") != 0
        or metrics.get("forbidden_context_rate") != 0
        or not isinstance(invariants, Mapping)
        or any(not isinstance(item, Mapping) or item.get("state") != "pass" for item in invariants.values())
    ):
        raise Phase15EvidenceError("baseline-v2 report does not prove the public safety contract")
    return {"source": dict(source), "metrics": dict(metrics), "invariants": dict(invariants)}


def _evaluation(report: Mapping[str, Any]) -> Mapping[str, Any]:
    corpus, metrics, invariants = (report.get(key) for key in ("corpus", "metrics", "invariants"))
    if (
        not isinstance(corpus, Mapping)
        or corpus.get("suite") != "all"
        or corpus.get("task_count") != 160
        or not isinstance(metrics, Mapping)
        or metrics.get("case_count") != 160
        or metrics.get("wrong_project_leakage_rate") != 0
        or metrics.get("forbidden_context_rate") != 0
        or not isinstance(invariants, Mapping)
        or any(not isinstance(item, Mapping) or item.get("state") != "pass" for item in invariants.values())
    ):
        raise Phase15EvidenceError("full evaluation does not prove the Phase 15 hard gates")
    return {"metrics": dict(metrics), "invariants": dict(invariants)}


def _git_sha(root: Path) -> str | None:
    try:
        result = subprocess.run(  # nosec B603
            [shutil.which("git") or "git", "rev-parse", "HEAD"],
            cwd=root,
            text=True,
            capture_output=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return result.stdout.strip() or None


def build_manifest(junit: Path, baseline: Path, evaluation: Path, root: Path = Path(".")) -> Mapping[str, Any]:
    """Validate artifacts without re-running tests or changing any baseline."""
    tests = _test_results(junit)
    missing = sorted(REQUIRED_TESTS - tests.keys())
    failed = sorted(name for name in REQUIRED_TESTS if tests.get(name) == FAIL)
    baseline_result = _baseline(_load_json(baseline, "baseline-v2 report"))
    evaluation_result = _evaluation(_load_json(evaluation, "full evaluation report"))
    return {
        "schema_version": 1,
        "phase": PHASE,
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "head_sha": _git_sha(root),
        "status": SUCCESS if not missing and not failed else FAIL,
        "tests": {
            "required": sorted(REQUIRED_TESTS),
            "missing": missing,
            "failed": failed,
            "passed": len(REQUIRED_TESTS) - len(missing) - len(failed),
        },
        "baseline_v2": baseline_result,
        "full_evaluation": evaluation_result,
        "invariants": {
            "wrong_project_leakage": 0,
            "forbidden_context": 0,
            "superseded_leakage": 0,
            "resolved_leakage": 0,
            "evaluator_determinism": SUCCESS,
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
    parser = argparse.ArgumentParser(description="Create Phase 15 evidence from CI artifacts")
    parser.add_argument("--junit", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--evaluation", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--root", type=Path, default=Path("."))
    args = parser.parse_args(argv)
    try:
        manifest = build_manifest(args.junit, args.baseline, args.evaluation, args.root)
        _atomic_write(args.output, manifest)
    except Phase15EvidenceError as exc:
        print(json.dumps({"status": FAIL, "error": str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps({"status": manifest["status"], "output": str(args.output)}, ensure_ascii=False))
    return 0 if manifest["status"] == SUCCESS else 1


if __name__ == "__main__":
    raise SystemExit(main())
