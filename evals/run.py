"""Offline CLI runner for deterministic Phase 15 evaluation suites."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Mapping, Sequence

from .baseline import BASELINE_PROVIDER_ID, BaselineContextProvider
from .authority_provider import AUTHORITY_PROVIDER_ID, AuthorityContextProvider
from .compiler_v2_provider import COMPILER_PROVIDER_ID, CompilerV2ContextProvider
from .router_provider import ROUTER_PROVIDER_ID, RouterContextProvider
from .corpus_builder import DEFAULT_CORPUS_ROOT, DEFAULT_FIXTURE_PATH, check_public_corpus
from .corpus_v2_builder import DEFAULT_CORPUS_ROOT as DEFAULT_CORPUS_V2_ROOT, check_corpus_v2
from .fixture_generator import build_vault
from .reporting import build_evaluation_report, write_evaluation_report
from .schema import load_fixture, load_tasks


DEFAULT_NOISE_COUNT = 24
SUITE_DIRECTORIES = {
    "smoke": ("test",),
    "public": ("dev", "test"),
    "holdout": ("holdout",),
    "all": ("dev", "test", "holdout"),
}


class EvaluationRunError(ValueError):
    """Raised when an evaluation suite cannot be constructed safely."""


def check_corpus(corpus_root: Path | str, fixture) -> None:
    """Validate the matching versioned corpus before it becomes evaluation input."""

    root = Path(corpus_root).resolve()
    if root == DEFAULT_CORPUS_V2_ROOT.resolve():
        check_corpus_v2(root, fixture)
    else:
        check_public_corpus(root, fixture)


def suite_task_paths(corpus_root: Path | str, suite: str) -> tuple[Path, ...]:
    """Return stable task paths for one named suite boundary."""

    if suite not in SUITE_DIRECTORIES:
        raise EvaluationRunError(f"unsupported evaluation suite: {suite}")
    root = Path(corpus_root)
    paths: list[Path] = []
    for directory in SUITE_DIRECTORIES[suite]:
        paths.extend((root / directory).glob("*.json"))
    ordered = tuple(sorted(paths))
    if not ordered:
        raise EvaluationRunError(f"evaluation suite has no task files: {suite}")
    return ordered


def run_evaluation(
    *,
    suite: str,
    provider: str = "baseline",
    fixture_path: Path | str = DEFAULT_FIXTURE_PATH,
    corpus_root: Path | str = DEFAULT_CORPUS_ROOT,
    seed: int = 0,
    noise_count: int = DEFAULT_NOISE_COUNT,
    source: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Run an offline synthetic vault through one supported provider and suite."""

    if provider not in {"baseline", "router", "authority", "compiler-v2"}:
        raise EvaluationRunError(f"unsupported evaluation provider: {provider}")
    fixture = load_fixture(fixture_path)
    check_corpus(corpus_root, fixture)
    tasks = load_tasks(suite_task_paths(corpus_root, suite), fixture)

    with TemporaryDirectory(prefix="brain-eleven-eval-") as directory:
        vault = build_vault(
            fixture,
            Path(directory) / "vault",
            seed=seed,
            noise_count=noise_count,
        )
        context_provider = {
            "baseline": BaselineContextProvider(),
            "router": RouterContextProvider(),
            "authority": AuthorityContextProvider(),
            "compiler-v2": CompilerV2ContextProvider(),
        }[provider]
        results = [context_provider.select(task, vault.root) for task in tasks]

    report_source: dict[str, Any] = {
        "fixture_seed": seed,
        "noise_count": noise_count,
        "runner": "phase15_offline",
    }
    if source:
        duplicate_keys = set(report_source) & set(source)
        if duplicate_keys:
            raise EvaluationRunError(
                f"custom source cannot override runner metadata: {sorted(duplicate_keys)}"
            )
        report_source.update(source)
    return build_evaluation_report(
        fixture,
        tasks,
        results,
        suite=suite,
        source=report_source,
    )


def _gate_failed(report: dict[str, Any]) -> bool:
    # An unsupported safety invariant is not a pass. A provider that cannot
    # prove scope/lifecycle isolation must not produce a green CLI result.
    return any(
        summary["state"] in {"fail", "unsupported"}
        for summary in report["invariants"].values()
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run an offline Brain-Eleven evaluation suite.")
    parser.add_argument("--provider", default="baseline", choices=("baseline", "router", "authority", "compiler-v2"))
    parser.add_argument("--suite", default="smoke", choices=tuple(SUITE_DIRECTORIES))
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE_PATH)
    parser.add_argument("--corpus-root", type=Path, default=DEFAULT_CORPUS_ROOT)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--noise-count", type=int, default=DEFAULT_NOISE_COUNT)
    parser.add_argument("--report", type=Path, help="Optional machine-readable report output path")
    args = parser.parse_args(argv)

    try:
        report = run_evaluation(
            suite=args.suite,
            provider=args.provider,
            fixture_path=args.fixture,
            corpus_root=args.corpus_root,
            seed=args.seed,
            noise_count=args.noise_count,
        )
    except (EvaluationRunError, ValueError) as error:
        parser.error(str(error))
    if args.report is not None:
        write_evaluation_report(args.report, report)

    output = {
        "provider": report["provider"]["id"],
        "suite": report["corpus"]["suite"],
        "case_count": report["metrics"]["case_count"],
        "context_precision": report["metrics"]["context_precision"],
        "context_recall": report["metrics"]["context_recall"],
        "gate": "fail" if _gate_failed(report) else "pass",
        "report": str(args.report) if args.report is not None else None,
    }
    print(json.dumps(output, sort_keys=True))
    return 1 if _gate_failed(report) else 0


if __name__ == "__main__":
    raise SystemExit(main())
