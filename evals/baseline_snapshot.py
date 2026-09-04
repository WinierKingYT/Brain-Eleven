"""Create and verify the committed, reproducible Phase 15 baseline snapshot."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Iterable, Sequence

from .reporting import EvaluationReportError, read_evaluation_report, write_evaluation_report
from .run import DEFAULT_NOISE_COUNT, run_evaluation


BASELINE_ID = "baseline-v1"
BASELINE_SUITE = "public"
BASELINE_SEED = 0
_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASELINE_PATH = _ROOT / "evals" / "reports" / f"{BASELINE_ID}.json"
_FINGERPRINT_PATHS = (
    # Keep this deliberately limited to the baseline provider and the shared
    # evaluation machinery it executes. Optional future providers (such as the
    # Phase 17 Router) must not invalidate an unchanged baseline merely by
    # adding their own adapter, shadow-report, or benchmark code.
    "evals/baseline.py",
    "evals/contracts.py",
    "evals/corpus_builder.py",
    "evals/fixture_generator.py",
    "evals/metrics.py",
    "evals/reporting.py",
    "evals/run.py",
    "evals/schema.py",
    "evals/fixtures/*.json",
    "evals/schemas/*.json",
    "evals/corpus/**/*.json",
    "scripts/context-compiler.py",
    "scripts/memory_scope.py",
    "scripts/memory_store.py",
    "scripts/project_registry.py",
)


class BaselineSnapshotError(ValueError):
    """Raised when the committed baseline no longer represents current inputs."""


def _source_paths(root: Path) -> tuple[Path, ...]:
    paths: set[Path] = set()
    for pattern in _FINGERPRINT_PATHS:
        paths.update(path for path in root.glob(pattern) if path.is_file())
    if not paths:
        raise BaselineSnapshotError("baseline source fingerprint has no files")
    return tuple(sorted(paths, key=lambda path: path.relative_to(root).as_posix()))


def source_fingerprint(root: Path | str = _ROOT) -> str:
    """Hash exact evaluation and retrieval inputs, excluding generated reports."""

    source_root = Path(root).resolve()
    digest = hashlib.sha256()
    for path in _source_paths(source_root):
        relative = path.relative_to(source_root).as_posix().encode("utf-8")
        digest.update(len(relative).to_bytes(4, "big"))
        digest.update(relative)
        content = path.read_bytes()
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
    return f"sha256:{digest.hexdigest()}"


def build_baseline_snapshot(root: Path | str = _ROOT) -> dict:
    """Run the public suite with fixed inputs and return the baseline report."""

    source_root = Path(root).resolve()
    return run_evaluation(
        suite=BASELINE_SUITE,
        fixture_path=source_root / "evals" / "fixtures" / "phase15-contract.json",
        corpus_root=source_root / "evals" / "corpus",
        seed=BASELINE_SEED,
        noise_count=DEFAULT_NOISE_COUNT,
        source={
            "baseline_id": BASELINE_ID,
            "source_fingerprint": source_fingerprint(source_root),
        },
    )


def write_baseline_snapshot(path: Path | str = DEFAULT_BASELINE_PATH, root: Path | str = _ROOT) -> dict:
    """Materialize the current deterministic baseline at its versioned path."""

    report = build_baseline_snapshot(root)
    write_evaluation_report(path, report)
    return report


def check_baseline_snapshot(path: Path | str = DEFAULT_BASELINE_PATH, root: Path | str = _ROOT) -> dict:
    """Refuse a stale or manually altered committed baseline snapshot."""

    expected = build_baseline_snapshot(root)
    actual = read_evaluation_report(path)
    if actual != expected:
        raise BaselineSnapshotError(
            "baseline-v1 differs from the deterministic current public-suite result"
        )
    return actual


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build or verify the Phase 15 baseline-v1 snapshot.")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true", help="write the deterministic baseline snapshot")
    mode.add_argument("--check", action="store_true", help="verify the committed snapshot without writing")
    parser.add_argument("--output", type=Path, default=DEFAULT_BASELINE_PATH)
    args = parser.parse_args(argv)

    try:
        report = (
            write_baseline_snapshot(args.output)
            if args.write
            else check_baseline_snapshot(args.output)
        )
    except (BaselineSnapshotError, EvaluationReportError, ValueError) as error:
        parser.error(str(error))
    print(
        json.dumps(
            {
            "baseline_id": BASELINE_ID,
            "case_count": report["metrics"]["case_count"],
            "context_precision": report["metrics"]["context_precision"],
            "context_recall": report["metrics"]["context_recall"],
            "status": "written" if args.write else "current",
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
