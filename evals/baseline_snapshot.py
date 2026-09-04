"""Create and verify versioned, reproducible Phase 15 baseline snapshots.

``baseline-v1`` is historical evidence.  It must remain byte-for-byte stable
even after later phases change a component that its original run happened to
exercise.  ``baseline-v2`` is the compatibility baseline for the graduated
160-task corpus and is the only snapshot compared with current inputs.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Iterable, Sequence

from .reporting import EvaluationReportError, read_evaluation_report, write_evaluation_report
from .run import DEFAULT_NOISE_COUNT, run_evaluation


BASELINE_V1_ID = "baseline-v1"
BASELINE_V2_ID = "baseline-v2"
# Keep these aliases for callers that ask for the current compatibility
# baseline.  Historical consumers must select V1 explicitly.
BASELINE_ID = BASELINE_V2_ID
BASELINE_SUITE = "public"
BASELINE_SEED = 0
_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASELINE_V1_PATH = _ROOT / "evals" / "reports" / f"{BASELINE_V1_ID}.json"
DEFAULT_BASELINE_V1_MANIFEST = _ROOT / "evals" / "reports" / f"{BASELINE_V1_ID}.manifest.json"
DEFAULT_BASELINE_V2_PATH = _ROOT / "evals" / "reports" / f"{BASELINE_V2_ID}.json"
DEFAULT_BASELINE_PATH = DEFAULT_BASELINE_V2_PATH
DEFAULT_CORPUS_V2_ROOT = _ROOT / "evals" / "corpus-v2"
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
    "evals/corpus-v2/**/*.json",
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
    """Hash exact V2 evaluation and retrieval inputs, excluding reports."""

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
    """Run the V2 public suite with fixed inputs and return its baseline."""

    source_root = Path(root).resolve()
    return run_evaluation(
        suite=BASELINE_SUITE,
        fixture_path=source_root / "evals" / "fixtures" / "phase15-contract.json",
        corpus_root=source_root / "evals" / "corpus-v2",
        seed=BASELINE_SEED,
        noise_count=DEFAULT_NOISE_COUNT,
        source={
            "baseline_id": BASELINE_ID,
            "source_fingerprint": source_fingerprint(source_root),
        },
    )


def write_baseline_snapshot(path: Path | str = DEFAULT_BASELINE_PATH, root: Path | str = _ROOT) -> dict:
    """Materialize the current deterministic V2 baseline at its versioned path."""

    report = build_baseline_snapshot(root)
    write_evaluation_report(path, report)
    return report


def check_baseline_snapshot(path: Path | str = DEFAULT_BASELINE_PATH, root: Path | str = _ROOT) -> dict:
    """Refuse a stale or manually altered current V2 baseline snapshot."""

    expected = build_baseline_snapshot(root)
    actual = read_evaluation_report(path)
    if actual != expected:
        raise BaselineSnapshotError(
            "baseline-v2 differs from the deterministic current public-suite result"
        )
    return actual


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(64 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def check_historical_baseline(
    path: Path | str = DEFAULT_BASELINE_V1_PATH,
    manifest_path: Path | str = DEFAULT_BASELINE_V1_MANIFEST,
) -> dict:
    """Verify V1 integrity without reinterpreting it through current code."""

    baseline_path = Path(path)
    manifest_file = Path(manifest_path)
    try:
        manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BaselineSnapshotError("baseline-v1 historical manifest is unreadable") from exc
    if not isinstance(manifest, dict) or set(manifest) != {
        "schema_version", "baseline_id", "foundation_sha", "report_sha256",
        "provider_version", "corpus_version", "metric_version", "public_case_count",
    }:
        raise BaselineSnapshotError("baseline-v1 historical manifest has an unsupported schema")
    if manifest["schema_version"] != 1 or manifest["baseline_id"] != BASELINE_V1_ID:
        raise BaselineSnapshotError("baseline-v1 historical manifest has an invalid identity")
    if manifest["report_sha256"] != _sha256(baseline_path):
        raise BaselineSnapshotError("baseline-v1 report does not match its historical manifest")
    report = read_evaluation_report(baseline_path)
    if report.get("source", {}).get("baseline_id") != BASELINE_V1_ID:
        raise BaselineSnapshotError("baseline-v1 report has the wrong identity")
    if report.get("metrics", {}).get("case_count") != manifest["public_case_count"]:
        raise BaselineSnapshotError("baseline-v1 report disagrees with its historical manifest")
    return report


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build or verify a versioned Phase 15 baseline snapshot.")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true", help="write the deterministic baseline snapshot")
    mode.add_argument("--check", action="store_true", help="verify the committed snapshot without writing")
    parser.add_argument("--baseline", choices=(BASELINE_V1_ID, BASELINE_V2_ID), default=BASELINE_V2_ID)
    parser.add_argument("--output", type=Path, default=DEFAULT_BASELINE_PATH)
    args = parser.parse_args(argv)
    if args.baseline == BASELINE_V1_ID and args.output == DEFAULT_BASELINE_PATH:
        args.output = DEFAULT_BASELINE_V1_PATH

    try:
        if args.baseline == BASELINE_V1_ID:
            if args.write:
                parser.error("baseline-v1 is immutable and cannot be rewritten")
            report = check_historical_baseline(args.output, DEFAULT_BASELINE_V1_MANIFEST)
        else:
            report = write_baseline_snapshot(args.output) if args.write else check_baseline_snapshot(args.output)
    except (BaselineSnapshotError, EvaluationReportError, ValueError) as error:
        parser.error(str(error))
    print(
        json.dumps(
            {
                "baseline_id": args.baseline,
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
