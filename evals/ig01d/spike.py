"""Throwaway semantic ceiling probe for IG01-D and R1.

The probe owns no production retrieval path. It builds the frozen synthetic
vault in a temporary directory, measures the current lexical compiler on the
same first 50 DEV cases, and optionally measures a real local embedding plus
cross-encoder pair. Persisted output contains only hashes, bounded provider
metadata, and aggregate metrics; benchmark text never leaves this process.
"""

from __future__ import annotations

import hashlib
import importlib.util
import argparse
import json
import math
import os
import re
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from brain_eleven.retrieval.embedding_provider import (
    EmbeddingProvider,
    EmbeddingStatus,
    LocalCrossEncoderReranker,
    Reranker,
    create_embedding_provider,
    create_reranker,
)

from ..baseline import BaselineContextProvider
from ..fixture_generator import build_vault
from ..schema import load_fixture, load_tasks
from .fingerprint import corpus_split_fingerprint


_K = 5
_RERANK_POOL = 20
_TURKISH_MARKERS = frozenset(
    {
        "bu", "bir", "için", "icin", "kullanacağız", "kullanacagiz", "proje",
        "kararı", "karari", "seçiyoruz", "seciyoruz", "nasıl", "nasil", "ve",
        "yalnız", "yalniz", "önce", "once", "güvenli", "guvenli", "kaydetme",
        "akışında", "akisinda", "olmalı", "olmali",
    }
)
_ENGLISH_MARKERS = frozenset(
    {
        "the", "this", "for", "use", "select", "record", "only", "context",
        "decision", "scenario", "project", "current", "find", "essential",
        "retrieve", "future", "rule", "case", "from", "with",
    }
)


def _provider_status() -> tuple[str, str]:
    if importlib.util.find_spec("sentence_transformers") is not None:
        return "sentence_transformers", "local embedding/cross-encoder package detected"
    if importlib.util.find_spec("openai") is not None:
        return "openai_only", "embedding client detected but no cross-encoder provider is installed"
    return "none", "no real embedding or cross-encoder provider is installed"


def configured_embedding_provider() -> EmbeddingProvider:
    """Return the config-gated embedding socket without running a probe."""

    return create_embedding_provider()


def configured_reranker_with_fallback() -> tuple[Reranker, str | None]:
    """Select the multilingual reranker and record a bounded fallback."""

    primary = create_reranker()
    if primary.provider_id != "unavailable-reranker":
        return primary, None
    if os.environ.get("IG_EMBEDDING_PROVIDER", "").strip().lower() != "local":
        return primary, None
    try:
        fallback = LocalCrossEncoderReranker(
            os.environ.get(
                "IG_LOCAL_RERANKER_FALLBACK_MODEL",
                "cross-encoder/ms-marco-MiniLM-L-6-v2",
            ),
            local_files_only=os.environ.get("IG_LOCAL_MODELS_LOCAL_FILES_ONLY", "").strip().lower() in {"1", "true", "yes", "on"},
        )
    except Exception:
        return primary, "cross-encoder/ms-marco-MiniLM-L-6-v2"
    return fallback, "cross-encoder/ms-marco-MiniLM-L-6-v2"


def _git_sha(root: Path) -> str:
    return subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip().lower()


def _sha(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def _language_bucket(document: Mapping[str, Any]) -> str:
    explicit = document.get("language")
    if explicit in {"tr", "en", "tr-en"}:
        return str(explicit)
    prompt = str(((document.get("task") or {}).get("prompt", ""))).lower()
    words = set(re.findall(r"[\wçğıöşüÇĞİÖŞÜ]+", prompt, flags=re.UNICODE))
    has_tr = bool(words & _TURKISH_MARKERS) or bool(re.search(r"[çğıöşü]", prompt))
    has_en = bool(words & _ENGLISH_MARKERS)
    if has_tr and has_en:
        return "tr-en"
    if has_tr:
        return "tr"
    return "en"


def _load_first_dev_cases(corpus_root: Path, fixture_path: Path, count: int) -> tuple[list[dict[str, Any]], Any]:
    files = sorted((corpus_root / "dev").glob("p15_*.json"))
    if len(files) < count:
        raise ValueError(f"IG01-D DEV corpus has fewer than {count} cases")
    fixture = load_fixture(fixture_path)
    tasks = load_tasks(tuple(files[:count]), fixture)
    documents = [json.loads(path.read_text(encoding="utf-8")) for path in files[:count]]
    if any("holdout" in task.task_id.lower() for task in tasks):
        raise ValueError("R1 feasibility probe cannot include HOLDOUT")
    return documents, (fixture, tasks)


def _read_records(vault: Path) -> dict[str, Mapping[str, Any]]:
    path = vault / ".claude" / "validated-memory.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    records = payload.get("validated_memory")
    if not isinstance(records, list):
        raise ValueError("synthetic vault has no validated memories")
    return {
        str(record["memory_id"]): record
        for record in records
        if isinstance(record, Mapping) and isinstance(record.get("memory_id"), str)
    }


def _allowed_records(records: Mapping[str, Mapping[str, Any]], project_id: str | None) -> list[Mapping[str, Any]]:
    allowed: list[Mapping[str, Any]] = []
    for record in records.values():
        if record.get("status") != "active":
            continue
        record_project = record.get("project_id") or None
        if project_id is None:
            if record_project is not None:
                continue
        elif record_project not in {None, project_id}:
            continue
        allowed.append(record)
    return sorted(allowed, key=lambda item: str(item["memory_id"]))


def _cosine(left: Sequence[float], right: Sequence[float]) -> float:
    if len(left) != len(right) or not left:
        raise ValueError("embedding dimensions differ")
    numerator = sum(float(a) * float(b) for a, b in zip(left, right))
    left_norm = math.sqrt(sum(float(value) ** 2 for value in left))
    right_norm = math.sqrt(sum(float(value) ** 2 for value in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return numerator / (left_norm * right_norm)


def _rank_semantic(
    *,
    task: Any,
    records: Mapping[str, Mapping[str, Any]],
    embedding_provider: EmbeddingProvider,
    reranker: Reranker,
) -> tuple[list[str], dict[str, Any]]:
    candidates = _allowed_records(records, task.project_id)
    texts = [str(record.get("content", "")) for record in candidates]
    embedded = embedding_provider.embed([task.prompt, *texts])
    if embedded.status != EmbeddingStatus.EMBEDDING_AVAILABLE.value:
        raise RuntimeError(f"embedding_unavailable:{embedded.error_code or 'unknown'}")
    if len(embedded.vectors) != len(candidates) + 1:
        raise RuntimeError("embedding_response_length_mismatch")
    query_vector = embedded.vectors[0]
    semantic_scores = [
        _cosine(query_vector, vector)
        for vector in embedded.vectors[1:]
    ]
    ordered = sorted(
        zip(candidates, semantic_scores),
        key=lambda item: (-item[1], str(item[0]["memory_id"])),
    )
    pool = ordered[:_RERANK_POOL]
    rerank_values = reranker.rerank(task.prompt, [str(item[0].get("content", "")) for item in pool])
    if rerank_values.status != EmbeddingStatus.EMBEDDING_AVAILABLE.value:
        raise RuntimeError(f"reranker_unavailable:{rerank_values.error_code or 'unknown'}")
    if len(rerank_values.scores) != len(pool):
        raise RuntimeError("reranker_response_length_mismatch")
    ranked = sorted(
        zip(pool, rerank_values.scores),
        key=lambda item: (-float(item[1]), -float(item[0][1]), str(item[0][0]["memory_id"])),
    )
    return [str(item[0][0]["memory_id"]) for item in ranked], {
        "embedding_provider": embedded.provider_id,
        "embedding_model": embedded.model,
        "reranker_provider": rerank_values.provider_id,
        "reranker_model": rerank_values.model,
    }


def _metric_row(retrieved: Sequence[str], required: Sequence[str], useful: Sequence[str], k: int = _K) -> dict[str, float | None]:
    top = list(retrieved[:k])
    relevant = set(required) | set(useful)
    relevant_count = sum(item in relevant for item in top)
    required_count = sum(item in set(required) for item in top)
    precision = relevant_count / len(top) if top else 0.0
    recall = required_count / len(set(required)) if required else None
    reciprocal_rank = 0.0
    for rank, item in enumerate(top, 1):
        if item in relevant:
            reciprocal_rank = 1.0 / rank
            break
    noise = (len(top) - relevant_count) / len(top) if top else 1.0
    return {
        "context_precision": precision,
        "recall_at_k": recall,
        "mandatory_recall": recall,
        "mrr": reciprocal_rank if relevant else None,
        "noise_ratio": noise,
    }


def _aggregate(rows: Iterable[Mapping[str, Any]]) -> dict[str, float | None]:
    rows = list(rows)
    names = ("context_precision", "recall_at_k", "mandatory_recall", "mrr", "noise_ratio")
    return {
        name: (
            sum(float(row[name]) for row in rows if row.get(name) is not None)
            / len([row for row in rows if row.get(name) is not None])
            if any(row.get(name) is not None for row in rows)
            else None
        )
        for name in names
    }


def _baseline_rows(tasks: Sequence[Any], fixture: Any, seed: int, noise_count: int, root: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="brain-eleven-r1-probe-") as directory:
        vault = build_vault(fixture, Path(directory) / "vault", seed=seed, noise_count=noise_count)
        provider = BaselineContextProvider()
        for task in tasks:
            selected = provider.select(task, vault.root)
            rows.append({
                "case_id": task.task_id,
                "selected_ids": [item.id for item in selected.selected_items],
            })
    del root
    return rows


def run_real_feasibility_probe(
    *,
    root: Path | str,
    corpus_root: Path | str,
    fixture_path: Path | str,
    git_sha: str,
    dev_case_count: int = 50,
    seed: int = 17,
    noise_count: int = 24,
    embedding_provider: EmbeddingProvider | None = None,
    reranker: Reranker | None = None,
) -> dict[str, Any]:
    """Run R1-a with the same public DEV boundary and frozen seed/noise."""

    if dev_case_count != 50 or seed != 17 or noise_count != 24:
        raise ValueError("R1-a is fixed at 50 DEV cases, seed 17 and noise 24")
    source_root = Path(root).resolve()
    corpus = Path(corpus_root).resolve()
    fixture_file = Path(fixture_path).resolve()
    revision = (git_sha or _git_sha(source_root)).lower()
    if not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise ValueError("git_sha must be a full lowercase 40-character SHA")
    documents, loaded = _load_first_dev_cases(corpus, fixture_file, dev_case_count)
    fixture, tasks = loaded
    selected_embedding = embedding_provider or configured_embedding_provider()
    selected_reranker, reranker_fallback = (reranker, None) if reranker is not None else configured_reranker_with_fallback()
    package_provider, package_reason = _provider_status()
    started = time.perf_counter()
    baseline_rows = _baseline_rows(tasks, fixture, seed, noise_count, source_root)
    baseline_by_id = {row["case_id"]: row for row in baseline_rows}
    baseline_metrics = _aggregate(
        [
            _metric_row(
                row["selected_ids"],
                tuple(document["expected_context"]["required"]),
                tuple(document["expected_context"]["useful"]),
            )
            for row, document in zip(baseline_rows, documents)
        ]
    )
    empty_metrics = {name: None for name in baseline_metrics}
    case_ids_hashed = [_sha(task.task_id) for task in tasks]
    baseline_languages: dict[str, Any] = {}
    for language in ("tr", "en", "tr-en"):
        language_rows = [
            (row, document)
            for row, document in zip(baseline_rows, documents)
            if _language_bucket(document) == language
        ]
        baseline_languages[language] = {
            "case_count": len(language_rows),
            "metrics": empty_metrics,
            "baseline_metrics": _aggregate([
                _metric_row(
                    row["selected_ids"],
                    tuple(document["expected_context"]["required"]),
                    tuple(document["expected_context"]["useful"]),
                )
                for row, document in language_rows
            ]),
        }
    base = {
        "status": "SEMANTIC_UNAVAILABLE",
        "provider_id": "sentence_transformers" if selected_embedding.provider_id != "unavailable" else package_provider,
        "reason": "no real embedding or cross-encoder provider is installed",
        "case_count": dev_case_count,
        "split": "dev",
        "holdout_included": False,
        "corpus_split_fingerprint": corpus_split_fingerprint(corpus),
        "precision": None,
        "empirical_ceiling": None,
        "elapsed_ms": 0.0,
        "measurement": "no score without a real embedding plus cross-encoder pair",
        "source_git_sha": revision,
        "seed": seed,
        "noise_count": noise_count,
        "k": _K,
        "rerank_pool": _RERANK_POOL,
        "embedding_model": getattr(selected_embedding, "model", "unavailable"),
        "reranker_model": getattr(selected_reranker, "model", "unavailable"),
        "reranker_fallback_model": reranker_fallback,
        "metrics": empty_metrics,
        "baseline_metrics": baseline_metrics,
        "per_language": baseline_languages,
        "case_ids_hashed": case_ids_hashed,
        "safety": {
            "wrong_project_leakage": 0,
            "forbidden_leakage": 0,
            "superseded_leakage": 0,
            "resolved_leakage": 0,
        },
    }
    if selected_embedding.provider_id == "unavailable":
        base["reason"] = package_reason if package_reason in {
            "no real embedding or cross-encoder provider is installed",
            "embedding client detected but no cross-encoder provider is installed",
            "provider detected; throwaway cross-encoder wiring is not part of production IG01-D",
        } else "no real embedding or cross-encoder provider is installed"
        base["elapsed_ms"] = round((time.perf_counter() - started) * 1000, 3)
        return {**base, "detail": {"provider_status": "embedding_unavailable"}}
    if selected_reranker.provider_id == "unavailable-reranker":
        base["reason"] = "embedding client detected but no cross-encoder provider is installed"
        base["provider_id"] = "sentence_transformers"
        base["elapsed_ms"] = round((time.perf_counter() - started) * 1000, 3)
        return {**base, "detail": {"provider_status": "reranker_unavailable"}}

    semantic_rows: list[dict[str, Any]] = []
    provider_identity: dict[str, Any] = {}
    safety = {"wrong_project_leakage": 0, "forbidden_leakage": 0, "superseded_leakage": 0, "resolved_leakage": 0}
    try:
        with tempfile.TemporaryDirectory(prefix="brain-eleven-r1-probe-") as directory:
            vault = build_vault(fixture, Path(directory) / "vault", seed=seed, noise_count=noise_count)
            records = _read_records(vault.root)
            for document, task in zip(documents, tasks):
                selected_ids, identity = _rank_semantic(
                    task=task,
                    records=records,
                    embedding_provider=selected_embedding,
                    reranker=selected_reranker,
                )
                provider_identity.update(identity)
                required = tuple(document["expected_context"]["required"])
                useful = tuple(document["expected_context"]["useful"])
                forbidden = set(document["expected_context"]["forbidden"])
                top = selected_ids[:_K]
                for memory_id in top:
                    record = records.get(memory_id)
                    if record is None:
                        safety["forbidden_leakage"] += 1
                        continue
                    if memory_id in forbidden:
                        safety["forbidden_leakage"] += 1
                    record_project = record.get("project_id") or None
                    if record_project not in {None, task.project_id}:
                        safety["wrong_project_leakage"] += 1
                    if record.get("status") == "superseded":
                        safety["superseded_leakage"] += 1
                    if record.get("status") == "resolved":
                        safety["resolved_leakage"] += 1
                semantic_rows.append({
                    "case_id": task.task_id,
                    "language": _language_bucket(document),
                    "metrics": _metric_row(selected_ids, required, useful),
                    "baseline_metrics": _metric_row(
                        baseline_by_id[task.task_id]["selected_ids"], required, useful,
                    ),
                })
    except RuntimeError as error:
        base["reason"] = "embedding client detected but no cross-encoder provider is installed" if str(error).startswith("reranker_unavailable") else "no real embedding or cross-encoder provider is installed"
        base["provider_id"] = "sentence_transformers"
        base["elapsed_ms"] = round((time.perf_counter() - started) * 1000, 3)
        return {**base, "detail": {"provider_status": str(error).split(":", 1)[0]}}

    metrics = _aggregate([row["metrics"] for row in semantic_rows])
    baseline_metrics = _aggregate([row["baseline_metrics"] for row in semantic_rows])
    languages = {}
    for language in ("tr", "en", "tr-en"):
        subset = [row for row in semantic_rows if row["language"] == language]
        languages[language] = {
            "case_count": len(subset),
            "metrics": _aggregate([row["metrics"] for row in subset]),
            "baseline_metrics": _aggregate([row["baseline_metrics"] for row in subset]),
        }
    base.update(
        {
            "status": "MEASURED",
            "provider_id": "sentence_transformers",
            "reason": "real embedding plus cross-encoder pair measured",
            "precision": metrics["context_precision"],
            "empirical_ceiling": metrics["context_precision"],
            "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
            "measurement": "precision measured on 50 DEV cases",
            "metrics": metrics,
            "baseline_metrics": baseline_metrics,
            "per_language": languages,
            "case_ids_hashed": case_ids_hashed,
            "safety": safety,
            "detail": {
                "source_git_sha": revision,
                "seed": seed,
                "noise_count": noise_count,
                "k": _K,
                "rerank_pool": _RERANK_POOL,
                "embedding_provider": provider_identity.get("embedding_provider"),
                "embedding_model": provider_identity.get("embedding_model"),
                "reranker_provider": provider_identity.get("reranker_provider"),
                "reranker_model": provider_identity.get("reranker_model"),
                "reranker_fallback_model": reranker_fallback,
                "metrics": metrics,
                "baseline_metrics": baseline_metrics,
                "per_language": languages,
                "case_ids_hashed": case_ids_hashed,
                "safety": safety,
                "holdout_included": False,
            },
        }
    )
    return base


def run_feasibility_probe(
    *,
    root: Path | str,
    corpus_root: Path | str,
    fixture_path: Path | str,
    git_sha: str,
    dev_case_count: int = 50,
    embedding_provider: EmbeddingProvider | None = None,
    reranker: Reranker | None = None,
    detailed: bool = False,
) -> dict[str, Any]:
    """Return the frozen IG01-D contract, or detailed R1 evidence on request."""

    result = run_real_feasibility_probe(
        root=root,
        corpus_root=corpus_root,
        fixture_path=fixture_path,
        git_sha=git_sha,
        dev_case_count=dev_case_count,
        embedding_provider=embedding_provider,
        reranker=reranker,
    )
    if detailed:
        return result
    return {
        key: result[key]
        for key in (
            "status", "provider_id", "reason", "case_count", "split", "holdout_included",
            "corpus_split_fingerprint", "precision", "empirical_ceiling", "elapsed_ms", "measurement",
        )
    }


__all__ = ["configured_embedding_provider", "configured_reranker_with_fallback", "run_feasibility_probe", "run_real_feasibility_probe"]


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the content-free IG01-D/R1 feasibility probe")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--corpus-root", type=Path, default=Path(__file__).resolve().parents[2] / "evals" / "corpus-v2")
    parser.add_argument("--fixture", type=Path, default=Path(__file__).resolve().parents[2] / "evals" / "fixtures" / "phase15-contract.json")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    result = run_real_feasibility_probe(
        root=args.root,
        corpus_root=args.corpus_root,
        fixture_path=args.fixture,
        git_sha=_git_sha(args.root),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "output": str(args.output),
        "status": result["status"],
        "case_count": result["case_count"],
        "holdout_included": result["holdout_included"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
