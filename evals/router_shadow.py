"""Content-free shadow comparison between baseline and Phase 17 routing."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence

from .reporting import compare_evaluation_reports
from .run import DEFAULT_CORPUS_ROOT, run_evaluation


SHADOW_REPORT_SCHEMA_VERSION = 1


def run_shadow_comparison(*, suite: str = "smoke", noise_count: int = 24, corpus_root: Path = DEFAULT_CORPUS_ROOT) -> dict[str, Any]:
    """Compare providers without changing ContextCompiler or SessionStart.

    Both evaluation reports intentionally contain identifiers and metrics only;
    memory content and task prompts stay inside the temporary synthetic vault.
    """
    baseline = run_evaluation(suite=suite, provider="baseline", noise_count=noise_count, corpus_root=corpus_root)
    router = run_evaluation(suite=suite, provider="router", noise_count=noise_count, corpus_root=corpus_root)
    comparison = compare_evaluation_reports(baseline, router)
    return {
        "schema_version": SHADOW_REPORT_SCHEMA_VERSION,
        "report_type": "brain_eleven_router_shadow_report",
        "rollout_mode": "SHADOW",
        "context_injection": False,
        "baseline_provider": baseline["provider"]["id"],
        "router_provider": router["provider"]["id"],
        "comparison": comparison,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compare baseline and Phase 17 shadow routing")
    parser.add_argument("--suite", choices=("smoke", "public", "holdout", "all"), default="smoke")
    parser.add_argument("--noise-count", type=int, default=24)
    parser.add_argument("--corpus-root", type=Path, default=DEFAULT_CORPUS_ROOT)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    report = run_shadow_comparison(suite=args.suite, noise_count=args.noise_count, corpus_root=args.corpus_root)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0 if report["comparison"]["candidate_gate"]["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
