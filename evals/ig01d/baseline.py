"""Run paired V1/V2 baselines under the frozen IG01-D contract."""

from __future__ import annotations

import argparse
import json
import subprocess
import time
from pathlib import Path
from typing import Any, Mapping, Sequence

from ..corpus_v2_builder import (
    _render,
    corpus_v2_manifest,
    validate_corpus_v2_documents,
)
from ..fixture_generator import build_vault
from ..reporting import compare_evaluation_reports
from ..run import run_evaluation, suite_task_paths
from ..schema import load_fixture, load_tasks
from .contracts import (
    EVALUATOR_VERSION,
    IG01D_SCHEMA_VERSION,
    PAIR_REPORT_TYPE,
    REPORT_TYPE,
    BaselineContractError,
    validate_baseline_report,
    validate_pair_report,
)
from .fingerprint import corpus_split_fingerprint, evaluation_source_fingerprint
from .spike import run_feasibility_probe


CORPUS_VERSION = "phase15-corpus-v2"
SEED = 17
NOISE_COUNT = 24
DEFAULT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_FIXTURE_PATH = DEFAULT_ROOT / "evals" / "fixtures" / "phase15-contract.json"
DEFAULT_CORPUS_ROOT = DEFAULT_ROOT / "evals" / "corpus-v2"


def _check_public_corpus_only(corpus_root: Path, fixture) -> None:
    """Validate public inputs without opening any HOLDOUT file."""

    documents = validate_corpus_v2_documents(fixture)
    expected = {
        corpus_root / relative
        for relative in documents
        if relative.parts[0] in {"dev", "test"}
    }
    actual = set()
    for split in ("dev", "test"):
        actual.update((corpus_root / split).glob("p15_*.json"))
    if actual != expected:
        raise BaselineContractError("IG01-D public corpus paths differ from the deterministic source")
    for relative, document in documents.items():
        if relative.parts[0] not in {"dev", "test"}:
            continue
        path = corpus_root / relative
        if path.read_text(encoding="utf-8") != _render(document):
            raise BaselineContractError(f"IG01-D public corpus content differs: {relative}")
    manifest_path = corpus_root / "manifest.json"
    if json.loads(manifest_path.read_text(encoding="utf-8")) != corpus_v2_manifest():
        raise BaselineContractError("IG01-D corpus manifest differs from the deterministic source")


def _git_sha(root: Path) -> str:
    result = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    )
    sha = result.stdout.strip().lower()
    if len(sha) != 40 or any(char not in "0123456789abcdef" for char in sha):
        raise BaselineContractError("git rev-parse HEAD did not return a full SHA")
    return sha


def _safe_case(case: Mapping[str, Any]) -> dict[str, Any]:
    """Copy only content-free fields from the legacy report case row."""

    allowed = (
        "task_id", "project_id", "expected", "selected_ids", "missing_required_ids",
        "unexpected_selected_ids", "forbidden_selected_ids", "metrics", "invariants",
        "violations", "passed",
    )
    result = {key: case[key] for key in allowed if key in case}
    # The legacy report's expected section contains only stable memory IDs.
    if not isinstance(result.get("task_id"), str) or not isinstance(result.get("selected_ids"), list):
        raise BaselineContractError("legacy case row is not content-free")
    return result


def _wrap_report(
    legacy: Mapping[str, Any],
    *,
    provider: str,
    git_sha: str,
    root: Path,
    corpus_root: Path,
    elapsed_ms: float,
) -> dict[str, Any]:
    split_fingerprint = corpus_split_fingerprint(corpus_root)
    source_fingerprint = evaluation_source_fingerprint(root, corpus_root)
    task_ids = list(legacy["corpus"]["task_ids"])
    report = {
        "schema_version": IG01D_SCHEMA_VERSION,
        "report_type": REPORT_TYPE,
        "evaluator_version": EVALUATOR_VERSION,
        "provider": {
            "id": legacy["provider"]["id"],
            "role": provider,
            "capabilities": {
                "selection": "existing_provider_adapter",
                "production_mutation": False,
            },
        },
        "corpus": {
            "corpus_version": CORPUS_VERSION,
            "fixture_id": legacy["corpus"]["fixture_id"],
            "suite": "public",
            "split": ["dev", "test"],
            "task_count": len(task_ids),
            "task_ids": task_ids,
            "split_fingerprint": split_fingerprint,
        },
        "source": {
            "git_sha": git_sha,
            "corpus_version": CORPUS_VERSION,
            "evaluator_version": EVALUATOR_VERSION,
            "evaluation_source_fingerprint": source_fingerprint,
            "seed": SEED,
            "noise_count": NOISE_COUNT,
        },
        "metrics": legacy["metrics"],
        "invariants": legacy["invariants"],
        "measurement": {
            "elapsed_ms": round(elapsed_ms, 3),
            "case_count": len(task_ids),
            "per_case_mean_ms": round(elapsed_ms / len(task_ids), 3),
            "p50_ms": None,
            "p95_ms": None,
            "budget_measurement": "token counts unavailable in normalized provider contract",
        },
        "cases": [_safe_case(case) for case in legacy["cases"]],
    }
    return validate_baseline_report(report)


def _derive_targets(v1: Mapping[str, Any], feasibility: Mapping[str, Any]) -> dict[str, Any]:
    """Derive visible, conservative targets without tuning either provider."""

    precision = float(v1["metrics"]["context_precision"])
    recall = float(v1["metrics"]["context_recall"])
    margin = 0.05
    realistic_gain = 0.10
    floors = {"context_precision": 0.60, "mandatory_recall": 0.80, "mrr": 0.85}
    targets = {
        "context_precision": {
            "value": round(max(floors["context_precision"] + margin, precision + realistic_gain), 6),
            "status": "PROVISIONAL_SPIKE_UNAVAILABLE" if feasibility["status"] != "MEASURED" else "DERIVED",
            "baseline": round(precision, 6),
        },
        "mandatory_recall": {
            "value": round(max(floors["mandatory_recall"] + margin, recall + realistic_gain), 6),
            "status": "PROVISIONAL_SPIKE_UNAVAILABLE" if feasibility["status"] != "MEASURED" else "DERIVED",
            "baseline": round(recall, 6),
        },
        "mrr": {
            "value": floors["mrr"],
            "status": "METRIC_UNAVAILABLE_IN_NORMALIZED_PROVIDER_CONTRACT",
            "baseline": None,
        },
    }
    return {
        "formula": "max(program_floor + margin, baseline + realistic_gain)",
        "margin": margin,
        "realistic_gain": realistic_gain,
        "program_floor": floors,
        "targets": targets,
        "quality_visibility": {
            "v2_must_exceed_v1": True,
            "promotion_allowed": False,
            "spike_status": feasibility["status"],
        },
    }


def build_pair_report(
    *,
    root: Path | str = DEFAULT_ROOT,
    fixture_path: Path | str = DEFAULT_FIXTURE_PATH,
    corpus_root: Path | str = DEFAULT_CORPUS_ROOT,
    git_sha: str | None = None,
    runner=run_evaluation,
    spike_runner=run_feasibility_probe,
) -> dict[str, Any]:
    """Run V1 and V2 with identical public inputs and return paired evidence."""

    source_root = Path(root).resolve()
    fixture_file = Path(fixture_path).resolve()
    corpus = Path(corpus_root).resolve()
    fixture = load_fixture(fixture_file)
    _check_public_corpus_only(corpus, fixture)
    tasks = load_tasks(suite_task_paths(corpus, "public"), fixture)
    task_ids = sorted(task.task_id for task in tasks)
    if not task_ids or any("holdout" in task_id.lower() for task_id in task_ids):
        raise BaselineContractError("IG01-D public suite contains an invalid or holdout task")
    revision = (git_sha or _git_sha(source_root)).lower()
    if len(revision) != 40 or any(char not in "0123456789abcdef" for char in revision):
        raise BaselineContractError("git_sha must be a full lowercase SHA")

    legacy_reports: dict[str, Mapping[str, Any]] = {}
    elapsed: dict[str, float] = {}
    for provider, key in (("baseline", "v1"), ("compiler-v2", "v2")):
        started = time.perf_counter()
        legacy_reports[key] = runner(
            suite="public",
            provider=provider,
            fixture_path=fixture_file,
            corpus_root=corpus,
            seed=SEED,
            noise_count=NOISE_COUNT,
            source={"ig01d_role": key},
        )
        elapsed[key] = (time.perf_counter() - started) * 1000
    v1 = _wrap_report(legacy_reports["v1"], provider="v1", git_sha=revision, root=source_root, corpus_root=corpus, elapsed_ms=elapsed["v1"])
    v2 = _wrap_report(legacy_reports["v2"], provider="v2", git_sha=revision, root=source_root, corpus_root=corpus, elapsed_ms=elapsed["v2"])
    if v1["corpus"]["task_ids"] != task_ids or v2["corpus"]["task_ids"] != task_ids:
        raise BaselineContractError("provider task IDs do not match the frozen public suite")
    comparison = compare_evaluation_reports(legacy_reports["v1"], legacy_reports["v2"])
    feasibility = spike_runner(root=source_root, corpus_root=corpus, fixture_path=fixture_file, git_sha=revision)
    report = {
        "schema_version": IG01D_SCHEMA_VERSION,
        "report_type": PAIR_REPORT_TYPE,
        "evaluator_version": EVALUATOR_VERSION,
        "corpus": {
            "corpus_version": CORPUS_VERSION,
            "fixture_id": fixture.fixture_id,
            "suite": "public",
            "split": ["dev", "test"],
            "task_count": len(task_ids),
            "task_ids": task_ids,
            "split_fingerprint": corpus_split_fingerprint(corpus),
        },
        "source": {
            "git_sha": revision,
            "corpus_version": CORPUS_VERSION,
            "evaluator_version": EVALUATOR_VERSION,
            "evaluation_source_fingerprint": evaluation_source_fingerprint(source_root, corpus),
            "seed": SEED,
            "noise_count": NOISE_COUNT,
        },
        "providers": {"v1": v1, "v2": v2},
        "comparison": comparison,
        "measurement": {
            "v1_elapsed_ms": round(elapsed["v1"], 3),
            "v2_elapsed_ms": round(elapsed["v2"], 3),
            "budget_measurement": "token counts unavailable in normalized provider contract",
        },
        "feasibility": feasibility,
        "target_derivation": _derive_targets(v1, feasibility),
    }
    return validate_pair_report(report)


def _atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def write_pair_report(path: Path | str, report: Mapping[str, Any]) -> None:
    _atomic_json(Path(path), validate_pair_report(report))


def read_pair_report(path: Path | str) -> dict[str, Any]:
    return validate_pair_report(json.loads(Path(path).read_text(encoding="utf-8")))


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the frozen IG01-D V1/V2 baseline measurement.")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE_PATH)
    parser.add_argument("--corpus-root", type=Path, default=DEFAULT_CORPUS_ROOT)
    args = parser.parse_args(argv)
    report = build_pair_report(root=args.root, fixture_path=args.fixture, corpus_root=args.corpus_root)
    write_pair_report(args.output, report)
    print(json.dumps({
        "report": str(args.output),
        "git_sha": report["source"]["git_sha"],
        "case_count": report["corpus"]["task_count"],
        "v1_precision": report["providers"]["v1"]["metrics"]["context_precision"],
        "v2_precision": report["providers"]["v2"]["metrics"]["context_precision"],
        "feasibility": report["feasibility"]["status"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
