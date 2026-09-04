"""Content-free Phase 19 shadow comparison; V1 and SessionStart remain untouched."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence

from .compiler_v2_evaluation import run_compiler_evaluation
from .reporting import compare_evaluation_reports
from .run import run_evaluation


REPORT_TYPE = "brain_eleven_compiler_v2_shadow_report"


def run_shadow_comparison(*, suite: str = "smoke", noise_count: int = 24) -> dict[str, Any]:
    """Compare V1 selection with V2 shadow output without injecting either result."""
    baseline = run_evaluation(suite=suite, provider="baseline", noise_count=noise_count)
    compiler = run_evaluation(suite=suite, provider="compiler-v2", noise_count=noise_count)
    comparison = compare_evaluation_reports(baseline, compiler)
    policy = run_compiler_evaluation(suite=suite)
    return {
        "schema_version": 1,
        "report_type": REPORT_TYPE,
        "rollout_mode": "SHADOW",
        "context_injection": False,
        "baseline_provider": baseline["provider"]["id"],
        "compiler_provider": compiler["provider"]["id"],
        "comparison": comparison,
        "compiler_policy_invariants": policy["invariants"],
        "compiler_policy_case_count": policy["case_count"],
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compare V1 baseline and V2 compiler in shadow mode")
    parser.add_argument("--suite", choices=("smoke", "public", "holdout", "all"), default="smoke")
    parser.add_argument("--noise-count", type=int, default=24)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    report = run_shadow_comparison(suite=args.suite, noise_count=args.noise_count)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    policy_ok = all(value["state"] == "pass" for value in report["compiler_policy_invariants"].values())
    return 0 if report["comparison"]["candidate_gate"]["passed"] and policy_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
