"""Content-free Phase 18 shadow comparison; no context is injected."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence

from .authority_evaluation import run_authority_evaluation
from .reporting import compare_evaluation_reports
from .run import run_evaluation


REPORT_TYPE = "brain_eleven_authority_shadow_report"


def run_shadow_comparison(*, suite: str = "smoke", noise_count: int = 24) -> dict[str, Any]:
    """Compare Router candidates with Authority annotations in SHADOW only."""
    router = run_evaluation(suite=suite, provider="router", noise_count=noise_count)
    authority = run_evaluation(suite=suite, provider="authority", noise_count=noise_count)
    comparison = compare_evaluation_reports(router, authority)
    authority_policy = run_authority_evaluation(suite=suite)
    return {
        "schema_version": 1,
        "report_type": REPORT_TYPE,
        "rollout_mode": "SHADOW",
        "context_injection": False,
        "router_provider": router["provider"]["id"],
        "authority_provider": authority["provider"]["id"],
        "comparison": comparison,
        "authority_policy_invariants": authority_policy["invariants"],
        "authority_policy_case_count": authority_policy["case_count"],
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compare Router and metadata authority in shadow mode")
    parser.add_argument("--suite", choices=("smoke", "public", "holdout", "all"), default="smoke")
    parser.add_argument("--noise-count", type=int, default=24)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    report = run_shadow_comparison(suite=args.suite, noise_count=args.noise_count)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    policy_ok = all(value["state"] == "pass" for value in report["authority_policy_invariants"].values())
    return 0 if report["comparison"]["candidate_gate"]["passed"] and policy_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
