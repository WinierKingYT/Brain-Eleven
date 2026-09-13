"""W-09A retrieval evaluation with a frozen, content-free evidence boundary."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from evals.baseline import BaselineContextProvider
from evals.compiler_v2_provider import CompilerV2ContextProvider
from evals.corpus_v2_builder import check_corpus_v2, check_corpus_v2_public
from evals.fixture_generator import build_vault
from evals.schema import GoldenTask, load_fixture, load_tasks

from .metrics import MetricError, metric_summary

ROOT = Path(__file__).resolve().parents[2]
CORPUS_ROOT = ROOT / "evals" / "corpus-v2"
FIXTURE = ROOT / "evals" / "fixtures" / "phase15-contract.json"
K_DEFAULT = 10
SEED_DEFAULT = 17
NOISE_DEFAULT = 24
_BANNED_KEYS = {
    "prompt", "query", "text", "content", "transcript", "message", "raw",
    "secret", "token", "password", "credential",
}
SOURCE_GLOBS = (
    "evals/baseline.py", "evals/compiler_v2_provider.py", "evals/fixture_generator.py",
    "evals/metrics.py", "evals/reporting.py", "evals/run.py", "evals/schema.py",
    "evals/fixtures/phase15-contract.json", "scripts/context-compiler.py",
    "scripts/task_state_context.py", "brain_eleven/memory/**/*.py", "brain_eleven/state/**/*.py",
    "brain_eleven/projects/**/*.py", "authority/**/*.py", "context_router/**/*.py",
    "context_compiler_v2/**/*.py", "evals/w09a/**/*.py", "tests/test_w09a_retrieval_evaluation.py",
)


class EvaluationError(ValueError):
    """Raised when an evaluation input or provider result is unsafe."""


def _hash_parts(parts: Iterable[tuple[str, bytes]]) -> str:
    digest = hashlib.sha256()
    for name, content in sorted(parts):
        encoded = name.encode("utf-8")
        digest.update(len(encoded).to_bytes(8, "big"))
        digest.update(encoded)
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
    return f"sha256:{digest.hexdigest()}"


def _normalized_bytes(path: Path) -> bytes:
    return path.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")


def _source_paths(root: Path) -> tuple[Path, ...]:
    paths: set[Path] = set()
    for pattern in SOURCE_GLOBS:
        matches = [root / pattern] if not any(char in pattern for char in "*?[") else root.glob(pattern)
        for path in matches:
            if path.is_symlink() or not path.is_file() or "__pycache__" in path.parts:
                continue
            if path.suffix == ".py" or path.as_posix().endswith("evals/fixtures/phase15-contract.json"):
                paths.add(path.resolve())
    explicit = {root / pattern for pattern in SOURCE_GLOBS if not any(char in pattern for char in "*?[")}
    if not all(path.is_file() and not path.is_symlink() for path in explicit):
        raise EvaluationError("W-09A source allowlist is unavailable")
    return tuple(sorted(paths, key=lambda path: path.relative_to(root).as_posix()))


def source_fingerprint(root: Path | str = ROOT) -> str:
    checkout = Path(root).resolve()
    return _hash_parts(
        (path.relative_to(checkout).as_posix(), _normalized_bytes(path))
        for path in _source_paths(checkout)
    )


def _manifest(root: Path) -> Mapping[str, Any]:
    try:
        manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise EvaluationError("W-09A corpus manifest is unavailable") from error
    if not isinstance(manifest, Mapping) or manifest.get("corpus_version") != 2 or manifest.get("schema_version") != 1:
        raise EvaluationError("W-09A corpus manifest is invalid")
    if manifest.get("suite_counts") != {"dev": 70, "test": 60, "holdout": 30}:
        raise EvaluationError("W-09A corpus split counts are invalid")
    return manifest


def corpus_fingerprint(root: Path | str = CORPUS_ROOT, *, split: str = "public") -> str:
    """Fingerprint exactly one public or holdout split; reject other names."""

    if split not in {"public", "holdout"}:
        raise EvaluationError("split must be public or holdout")
    corpus = Path(root).resolve()
    _manifest(corpus)
    directories = ("dev", "test") if split == "public" else ("holdout",)
    paths = [corpus / "manifest.json"]
    for directory in directories:
        files = sorted((corpus / directory).glob("*.json"))
        if any(path.is_symlink() for path in files):
            raise EvaluationError("W-09A corpus must not contain symlinks")
        paths.extend(files)
    expected_count = 1 + (130 if split == "public" else 30)
    if len(paths) != expected_count:
        raise EvaluationError("W-09A corpus split is incomplete")
    return _hash_parts(
        (path.relative_to(ROOT).as_posix(), _normalized_bytes(path)) for path in paths
    )


def load_split(
    *, split: str = "public", root: Path = CORPUS_ROOT, fixture_path: Path = FIXTURE
) -> tuple[GoldenTask, ...]:
    if split not in {"public", "holdout"}:
        raise EvaluationError("split must be public or holdout")
    fixture = load_fixture(fixture_path)
    corpus = root.resolve()
    if split == "public":
        check_corpus_v2_public(corpus, fixture)
        directories = ("dev", "test")
    else:
        check_corpus_v2(corpus, fixture)
        directories = ("holdout",)
    paths = [path for directory in directories for path in sorted((corpus / directory).glob("*.json"))]
    return load_tasks(paths, fixture)


def load_public_tasks(*, root: Path = CORPUS_ROOT, fixture_path: Path = FIXTURE, split: str = "public") -> tuple[GoldenTask, ...]:
    """Compatibility wrapper retained for the initial W-09A test surface."""

    return load_split(split=split, root=root, fixture_path=fixture_path)


def _git_sha(root: Path = ROOT) -> str:
    try:
        value = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError) as error:
        raise EvaluationError("git revision is unavailable") from error
    if not re.fullmatch(r"[0-9a-f]{40}", value):
        raise EvaluationError("git revision is invalid")
    return value


def _task_fingerprint(task: GoldenTask, candidate_ids: Sequence[str]) -> str:
    payload = {
        "task_id": task.task_id,
        "project_id": task.project_id,
        "query_sha256": hashlib.sha256(task.prompt.encode("utf-8")).hexdigest(),
        "intent": list(task.intent),
        "domains": list(task.domains),
        "required": sorted(task.required),
        "useful": sorted(task.useful),
        "forbidden": sorted(task.forbidden),
        "candidate_ids": list(candidate_ids),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _snapshot(vault: Path) -> tuple[int, tuple[str, ...], dict[str, dict[str, Any]], str, str]:
    path = vault / ".claude" / "validated-memory.json"
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
        revision = document["revision"]
        records = document["validated_memory"]
    except (OSError, KeyError, TypeError, json.JSONDecodeError) as error:
        raise EvaluationError("generated canonical memory snapshot is invalid") from error
    if isinstance(revision, bool) or not isinstance(revision, int) or revision < 0 or not isinstance(records, list):
        raise EvaluationError("generated canonical memory snapshot is invalid")
    metadata: dict[str, dict[str, Any]] = {}
    ordered: list[str] = []
    content_rows: list[dict[str, Any]] = []
    for record in records:
        if not isinstance(record, Mapping) or not isinstance(record.get("memory_id"), str) or record["memory_id"] in metadata:
            raise EvaluationError("generated canonical memory snapshot has invalid IDs")
        memory_id = record["memory_id"]
        ordered.append(memory_id)
        project_id = record.get("project_id") or None
        metadata[memory_id] = {
            "project_id": project_id,
            "status": record.get("status"),
            "type": record.get("type"),
        }
        content_rows.append({
            "memory_id": memory_id,
            "type": record.get("type"),
            "status": record.get("status"),
            "scope": record.get("scope"),
            "project_id": project_id,
            "content": record.get("content"),
            "source_revision": revision,
        })
    content = json.dumps(
        sorted(content_rows, key=lambda row: row["memory_id"]),
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    order = json.dumps(ordered, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return (
        revision,
        tuple(ordered),
        metadata,
        _hash_parts((("validated_memory.json", content),)),
        _hash_parts((("candidate-order.json", order),)),
    )


def _content_free(value: Any) -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            lowered = str(key).lower()
            if lowered in _BANNED_KEYS or any(marker in lowered for marker in ("prompt", "transcript", "secret", "password", "credential")):
                raise EvaluationError("W-09A report is not content-free")
            _content_free(child)
    elif isinstance(value, list):
        for child in value:
            _content_free(child)


def _validate_labels(task: GoldenTask, candidates: Sequence[str]) -> None:
    candidate_set = set(candidates)
    labels = [tuple(sorted(values)) for values in (task.required, task.useful, task.forbidden)]
    if any(len(values) != len(set(values)) for values in labels):
        raise EvaluationError(f"invalid duplicate labels for {task.task_id}")
    if not all(set(values) <= candidate_set for values in labels):
        raise EvaluationError(f"labels reference missing candidate for {task.task_id}")
    if (
        set(labels[0]) & set(labels[1])
        or set(labels[0]) & set(labels[2])
        or set(labels[1]) & set(labels[2])
    ):
        raise EvaluationError(f"labels overlap for {task.task_id}")


def evaluate_selection(
    task: GoldenTask,
    selected_ids: Iterable[str],
    *,
    k: int,
    candidate_ids: Iterable[str],
    candidate_metadata: Mapping[str, Mapping[str, Any]],
    token_counts: Mapping[str, int] | None = None,
) -> dict[str, Any]:
    candidates = tuple(candidate_ids)
    if len(candidates) != len(set(candidates)):
        raise EvaluationError("candidate IDs must be unique")
    _validate_labels(task, candidates)
    selected = tuple(selected_ids)
    if any(value not in candidate_metadata for value in selected):
        raise EvaluationError("provider selected an unknown candidate")
    metrics = metric_summary(
        selected,
        sorted(task.required),
        sorted(task.useful),
        sorted(task.required),
        k=k,
        token_counts=token_counts,
    )
    forbidden = sum(value in task.forbidden for value in selected)
    wrong_project = sum(
        task.project_id is not None
        and candidate_metadata[value].get("project_id") not in (None, task.project_id)
        for value in selected
    )
    superseded = sum(
        str(candidate_metadata[value].get("status")).lower() == "superseded"
        for value in selected
    )
    resolved = sum(
        str(candidate_metadata[value].get("status")).lower() == "resolved"
        for value in selected
    )
    return {
        "task_id": task.task_id,
        "selected_ids": list(selected),
        "metrics": {
            "precision": metrics.precision,
            "recall": metrics.recall,
            "f1": metrics.f1,
            "mrr": metrics.mrr,
            "mandatory_recall": metrics.mandatory_recall,
            "noise_ratio": metrics.noise_ratio,
            "token_waste": metrics.token_waste,
            "selected_count": metrics.selected_count,
        },
        "safety": {
            "wrong_project_leakage": wrong_project,
            "forbidden_leakage": forbidden,
            "superseded_leakage": 0 if task.inactive_allowed else superseded,
            "resolved_leakage": 0 if task.inactive_allowed else resolved,
        },
    }


def _provider(provider_id: str):
    if provider_id == "v1":
        return BaselineContextProvider(), "context_compiler_baseline_v1"
    if provider_id == "v2":
        return CompilerV2ContextProvider(), "context_compiler_v2"
    raise EvaluationError("provider must be v1 or v2")


def run_provider(
    *,
    provider_id: str,
    split: str = "public",
    k: int = K_DEFAULT,
    seed: int = SEED_DEFAULT,
    noise_count: int = NOISE_DEFAULT,
    root: Path = ROOT,
    corpus_root: Path = CORPUS_ROOT,
    fixture_path: Path = FIXTURE,
) -> dict[str, Any]:
    tasks = load_split(split=split, root=corpus_root, fixture_path=fixture_path)
    fixture = load_fixture(fixture_path)
    provider, provider_name = _provider(provider_id)
    corpus_fp = corpus_fingerprint(corpus_root, split=split)
    source_fp = source_fingerprint(root)
    with tempfile.TemporaryDirectory(prefix="brain-eleven-w09a-") as directory:
        generated = build_vault(fixture, Path(directory) / "vault", seed=seed, noise_count=noise_count)
        revision, candidate_ids, metadata, content_fp, order_fp = _snapshot(generated.root)
        rows: list[dict[str, Any]] = []
        for task in tasks:
            try:
                result = provider.select(task, generated.root)
                row = evaluate_selection(
                    task,
                    (item.id for item in result.selected_items),
                    k=k,
                    candidate_ids=candidate_ids,
                    candidate_metadata=metadata,
                )
                row["status"] = "scored"
            except (EvaluationError, MetricError, RuntimeError, ValueError) as error:
                row = {
                    "task_id": task.task_id,
                    "selected_ids": [],
                    "status": "invalid",
                    "error_code": type(error).__name__,
                }
            row["task_fingerprint"] = _task_fingerprint(task, candidate_ids)
            rows.append(row)
    scored = [row for row in rows if row["status"] == "scored"]
    invalid = len(rows) - len(scored)

    def average(name: str) -> float | None:
        values = [row["metrics"][name] for row in scored if row["metrics"][name] is not None]
        return sum(values) / len(values) if values else None

    safety_names = (
        "wrong_project_leakage", "forbidden_leakage", "superseded_leakage", "resolved_leakage"
    )
    safety_totals = {
        name: sum(row.get("safety", {}).get(name, 0) for row in scored)
        for name in safety_names
    }
    quality_state = "measured" if not invalid else "invalid"
    safety_state = "fail" if any(safety_totals.values()) else "pass" if not invalid else "unsupported"
    report = {
        "schema_version": 1,
        "report_type": "brain_eleven_w09a_provider",
        "provider": {
            "id": provider_name,
            "role": provider_id,
            "state": "available",
            "configuration_id": "phase15-offline-v1",
        },
        "corpus": {
            "version": 2,
            "split": split,
            "task_count": len(tasks),
            "task_ids": [task.task_id for task in tasks],
            "fingerprint": corpus_fp,
        },
        "source": {
            "git_sha": _git_sha(root),
            "source_fingerprint": source_fp,
            "fixture_seed": seed,
            "noise_count": noise_count,
            "retrieval_k": k,
            "normalization": "first_k_provider_order",
            "tie_break": "provider_order",
            "candidate_content_fingerprint": content_fp,
            "candidate_order_fingerprint": order_fp,
            "source_memory_revision": revision,
        },
        "metrics": {
            "case_count": len(scored),
            "invalid_case_count": invalid,
            "precision_at_k": average("precision"),
            "recall_at_k": average("recall"),
            "f1": average("f1"),
            "mrr": average("mrr"),
            "mandatory_recall": average("mandatory_recall"),
            "noise_ratio": average("noise_ratio"),
            "token_waste": "unavailable",
        },
        "safety": {**safety_totals, "state": safety_state},
        "quality": {"state": quality_state, "excluded_case_count": 0, "answerability_no_count": 0},
        "measurement": {"state": "complete" if quality_state == "measured" else "incomplete"},
        "promotion": "blocked",
        "cases": rows,
    }
    _content_free(report)
    return report


def compare_providers(
    *, split: str = "public", k: int = K_DEFAULT, seed: int = SEED_DEFAULT,
    noise_count: int = NOISE_DEFAULT, root: Path = ROOT, corpus_root: Path = CORPUS_ROOT,
    fixture_path: Path = FIXTURE,
) -> dict[str, Any]:
    v1 = run_provider(provider_id="v1", split=split, k=k, seed=seed, noise_count=noise_count, root=root, corpus_root=corpus_root, fixture_path=fixture_path)
    v2 = run_provider(provider_id="v2", split=split, k=k, seed=seed, noise_count=noise_count, root=root, corpus_root=corpus_root, fixture_path=fixture_path)
    same_input = (
        v1["corpus"] == v2["corpus"]
        and v1["source"]["candidate_content_fingerprint"] == v2["source"]["candidate_content_fingerprint"]
        and v1["source"]["candidate_order_fingerprint"] == v2["source"]["candidate_order_fingerprint"]
        and [row["task_fingerprint"] for row in v1["cases"]] == [row["task_fingerprint"] for row in v2["cases"]]
    )
    result = {
        "schema_version": 1,
        "report_type": "brain_eleven_w09a_pair",
        "same_input": same_input,
        "corpus": v1["corpus"],
        "source": {
            "git_sha": v1["source"]["git_sha"],
            "source_fingerprint": v1["source"]["source_fingerprint"],
            "candidate_content_fingerprint": v1["source"]["candidate_content_fingerprint"],
            "candidate_order_fingerprint": v1["source"]["candidate_order_fingerprint"],
            "retrieval_k": k,
            "seed": seed,
            "normalization": "first_k_provider_order",
            "tie_break": "provider_order",
        },
        "providers": {
            "v1": {"id": v1["provider"]["id"], "quality": v1["quality"], "metrics": v1["metrics"], "safety": v1["safety"]},
            "v2": {"id": v2["provider"]["id"], "quality": v2["quality"], "metrics": v2["metrics"], "safety": v2["safety"]},
        },
        "evaluation_status": {
            "evidence": "verified" if same_input else "tampered",
            "quality": "measured" if v1["quality"]["state"] == v2["quality"]["state"] == "measured" else "unavailable",
            "measurement": "complete" if same_input else "incomplete",
            "promotion": "blocked",
        },
    }
    _content_free(result)
    return result


def control_metrics(*, mode: str, candidate_ids: Sequence[str], required: Sequence[str], useful: Sequence[str], k: int | None = None) -> dict[str, Any]:
    if mode not in {"all", "none"}:
        raise EvaluationError("control mode must be all or none")
    selected = tuple(candidate_ids) if mode == "all" else tuple()
    metrics = metric_summary(selected, sorted(required), sorted(useful), sorted(required), k=k or max(len(candidate_ids), 1))
    return {"precision": metrics.precision, "recall": metrics.recall, "noise_ratio": metrics.noise_ratio, "token_waste": metrics.token_waste}


def write_report(path: Path | str, report: Mapping[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the bounded W-09A retrieval evaluation.")
    parser.add_argument("--provider", choices=("v1", "v2", "both"), default="both")
    parser.add_argument("--split", choices=("public", "holdout"), default="public")
    parser.add_argument("--k", type=int, default=K_DEFAULT)
    parser.add_argument("--seed", type=int, default=SEED_DEFAULT)
    parser.add_argument("--noise-count", type=int, default=NOISE_DEFAULT)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args(argv)
    report = compare_providers(split=args.split, k=args.k, seed=args.seed, noise_count=args.noise_count) if args.provider == "both" else run_provider(provider_id=args.provider, split=args.split, k=args.k, seed=args.seed, noise_count=args.noise_count)
    if args.report:
        write_report(args.report, report)
    print(json.dumps({"provider": args.provider, "split": args.split, "quality": report.get("quality", report.get("evaluation_status", {}).get("quality")), "evidence": report.get("evaluation_status", {}).get("evidence", "verified")}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
