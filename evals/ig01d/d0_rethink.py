"""D0 retrieval rethink probes: corpus balance, tuned models, and hybrid RRF.

This module is evaluation-only. It never imports canonical writers and never
changes production retrieval configuration. Reports contain hashes, model
availability, and aggregate metrics only.
"""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile
from typing import Any, Mapping, Sequence

from brain_eleven.retrieval.embedding_provider import (
    EmbeddingProvider,
    LocalCrossEncoderReranker,
    LocalSentenceTransformerProvider,
    Reranker,
)

from ..baseline import BaselineContextProvider
from ..fixture_generator import build_vault
from .spike import (
    _aggregate,
    _allowed_records,
    _language_bucket,
    _load_first_dev_cases,
    _metric_row,
    _rank_semantic,
    _read_records,
)


ROOT = Path(__file__).resolve().parents[2]
IG01B_DEV = ROOT / "evals" / "ig01b" / "public" / "ig-eval-v2" / "dev.jsonl"
IG01D_CORPUS = ROOT / "evals" / "corpus-v2"
FIXTURE_PATH = ROOT / "evals" / "fixtures" / "phase15-contract.json"
SEED = 17
NOISE_COUNT = 24
K = 5
MIN_BALANCED_CASES = 100
LANGUAGES = ("en", "tr", "tr-en")


def _git_sha(root: Path = ROOT) -> str:
    return subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip().lower()


def _hash(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def _ig01b_census(path: Path = IG01B_DEV) -> dict[str, Any]:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    languages = Counter(str(row.get("language", "unknown")) for row in rows)
    answerability = Counter(
        str((row.get("answerability") or {}).get("status", "unknown"))
        for row in rows
    )
    categories = Counter(str(row.get("category", "unknown")) for row in rows)
    answerable = sum(1 for row in rows if (row.get("answerability") or {}).get("status") == "answerable")
    language_fractions = {
        language: round(languages.get(language, 0) / len(rows), 6) if rows else None
        for language in LANGUAGES
    }
    return {
        "path": "evals/ig01b/public/ig-eval-v2/dev.jsonl",
        "corpus_version": "ig-eval-v2",
        "dataset_class": "PUBLIC_SYNTHETIC",
        "case_count": len(rows),
        "answerable_case_count": answerable,
        "language_counts": {language: languages.get(language, 0) for language in LANGUAGES},
        "language_fractions": language_fractions,
        "answerability_counts": dict(sorted(answerability.items())),
        "category_counts": dict(sorted(categories.items())),
        "language_balance_min_fraction": min(
            (language_fractions[language] or 0.0 for language in LANGUAGES),
            default=0.0,
        ),
        "target_min_cases": MIN_BALANCED_CASES,
        "status": (
            "BALANCED_LANGUAGE_STRATA_CASE_COUNT_BELOW_TARGET"
            if len(rows) < MIN_BALANCED_CASES
            else "PASS"
        ),
    }


class _E5PrefixedProvider:
    """Add the E5 query/passage contract without altering production adapters."""

    def __init__(self, provider: EmbeddingProvider) -> None:
        self._provider = provider
        self.provider_id = provider.provider_id
        self.model = provider.model + " [query/passage-prefix]"

    def embed(self, texts: Sequence[str]):
        values = list(texts)
        prefixed = [
            ("query: " if index == 0 else "passage: ") + text
            for index, text in enumerate(values)
        ]
        return self._provider.embed(prefixed)


def _scope_safe(record: Mapping[str, Any], project_id: str | None) -> bool:
    record_project = record.get("project_id") or None
    return record_project in {None, project_id}


def _rrf(semantic_ids: Sequence[str], lexical_ids: Sequence[str]) -> list[str]:
    scores: Counter[str] = Counter()
    for rank, memory_id in enumerate(semantic_ids, 1):
        scores[memory_id] += 1.0 / (60.0 + rank)
    for rank, memory_id in enumerate(lexical_ids, 1):
        scores[memory_id] += 1.0 / (60.0 + rank)
    return [
        memory_id
        for memory_id, _ in sorted(scores.items(), key=lambda item: (-item[1], item[0]))
    ]


def _safety_counts(
    selected_ids: Sequence[str],
    records: Mapping[str, Mapping[str, Any]],
    task: Any,
    forbidden: set[str],
) -> dict[str, int]:
    counts = {
        "wrong_project_leakage": 0,
        "forbidden_leakage": 0,
        "superseded_leakage": 0,
        "resolved_leakage": 0,
    }
    for memory_id in selected_ids[:K]:
        record = records.get(memory_id)
        if record is None:
            counts["forbidden_leakage"] += 1
            continue
        if memory_id in forbidden:
            counts["forbidden_leakage"] += 1
        if not _scope_safe(record, task.project_id):
            counts["wrong_project_leakage"] += 1
        if record.get("status") == "superseded":
            counts["superseded_leakage"] += 1
        if record.get("status") == "resolved":
            counts["resolved_leakage"] += 1
    return counts


def _run_variant(
    name: str,
    embedding_provider: EmbeddingProvider,
    reranker: Reranker,
    documents: Sequence[Mapping[str, Any]],
    tasks: Sequence[Any],
    fixture: Any,
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    safety = Counter()
    identities: set[tuple[str, ...]] = set()
    baseline = BaselineContextProvider()
    with tempfile.TemporaryDirectory(prefix="brain-eleven-d0-") as directory:
        vault = build_vault(
            fixture,
            Path(directory) / "vault",
            seed=SEED,
            noise_count=NOISE_COUNT,
        )
        records = _read_records(vault.root)
        for document, task in zip(documents, tasks):
            lexical = baseline.select(task, vault.root)
            lexical_ids = [str(item.id) for item in lexical.selected_items]
            semantic_ids, identity = _rank_semantic(
                task=task,
                records=records,
                embedding_provider=embedding_provider,
                reranker=reranker,
            )
            selected_ids = (
                _rrf(semantic_ids, lexical_ids)
                if name.endswith("hybrid")
                else semantic_ids
            )
            required = tuple(document["expected_context"]["required"])
            useful = tuple(document["expected_context"]["useful"])
            forbidden = set(document["expected_context"]["forbidden"])
            metrics = _metric_row(selected_ids, required, useful)
            rows.append({"language": _language_bucket(document), **metrics})
            safety.update(_safety_counts(selected_ids, records, task, forbidden))
            identities.add(tuple(str(identity.get(key, "")) for key in (
                "embedding_provider", "embedding_model", "reranker_provider", "reranker_model",
            )))
    metrics = _aggregate(rows)
    per_language = {}
    for language in LANGUAGES:
        subset = [row for row in rows if row["language"] == language]
        per_language[language] = {
            "case_count": len(subset),
            "metrics": _aggregate(subset),
        }
    return {
        "status": "MEASURED",
        "variant": name,
        "provider_identity": [
            {
                "embedding_provider": identity[0],
                "embedding_model": identity[1],
                "reranker_provider": identity[2],
                "reranker_model": identity[3],
            }
            for identity in sorted(identities)
        ],
        "metrics": metrics,
        "per_language": per_language,
        "safety": dict(sorted(safety.items())),
        "case_count": len(rows),
        "scope_filter": "current_project_plus_global",
        "production_mutation": False,
    }


def _try_tuned_provider() -> tuple[dict[str, Any], EmbeddingProvider | None, Reranker | None]:
    attempts = (
        (
            "intfloat/multilingual-e5-large",
            "cross-encoder/mmarco-mMiniLMv2-L12-H384-v1",
            True,
        ),
        ("BAAI/bge-m3", "BAAI/bge-reranker-v2-m3", False),
    )
    failures: list[dict[str, str]] = []
    for embedding_model, reranker_model, e5_prefix in attempts:
        try:
            embedding: EmbeddingProvider = LocalSentenceTransformerProvider(
                embedding_model,
                local_files_only=True,
            )
            if e5_prefix:
                embedding = _E5PrefixedProvider(embedding)
            reranker = LocalCrossEncoderReranker(
                reranker_model,
                local_files_only=True,
            )
            return (
                {
                    "status": "AVAILABLE",
                    "embedding_model": embedding_model,
                    "reranker_model": reranker_model,
                    "prefix_contract": "query/passage" if e5_prefix else "none",
                    "attempts": failures,
                },
                embedding,
                reranker,
            )
        except Exception as error:
            failures.append({
                "embedding_model": embedding_model,
                "reranker_model": reranker_model,
                "reason": type(error).__name__ + ":" + str(error)[:96],
            })
    return (
        {
            "status": "UNAVAILABLE",
            "embedding_model": attempts[0][0],
            "reranker_model": attempts[0][1],
            "attempts": failures,
            "reason": "retrieval-tuned local model is not available in the offline cache",
        },
        None,
        None,
    )


def run_d0_probe(
    *,
    root: Path = ROOT,
    corpus_root: Path = IG01D_CORPUS,
    fixture_path: Path = FIXTURE_PATH,
    ig01b_dev_path: Path = IG01B_DEV,
) -> dict[str, Any]:
    revision = _git_sha(root)
    files = sorted((corpus_root / "dev").glob("p15_*.json"))
    documents, loaded = _load_first_dev_cases(corpus_root, fixture_path, len(files))
    fixture, tasks = loaded
    census = _ig01b_census(ig01b_dev_path)
    variants: dict[str, Any] = {}
    try:
        mpnet = LocalSentenceTransformerProvider(
            "sentence-transformers/paraphrase-multilingual-mpnet-base-v2",
            local_files_only=True,
        )
        reranker = LocalCrossEncoderReranker(
            "cross-encoder/mmarco-mMiniLMv2-L12-H384-v1",
            local_files_only=True,
        )
        variants["mpnet_scope_filtered"] = _run_variant(
            "mpnet_scope_filtered",
            mpnet,
            reranker,
            documents,
            tasks,
            fixture,
        )
        variants["mpnet_hybrid"] = _run_variant(
            "mpnet_hybrid",
            mpnet,
            reranker,
            documents,
            tasks,
            fixture,
        )
        mpnet_status: dict[str, Any] = {"status": "AVAILABLE"}
    except Exception as error:
        mpnet_status = {
            "status": "UNAVAILABLE",
            "reason": type(error).__name__ + ":" + str(error)[:96],
        }
    tuned_status, tuned_embedding, tuned_reranker = _try_tuned_provider()
    if tuned_embedding is not None and tuned_reranker is not None:
        variants["tuned_scope_filtered"] = _run_variant(
            "tuned_scope_filtered",
            tuned_embedding,
            tuned_reranker,
            documents,
            tasks,
            fixture,
        )
        variants["tuned_hybrid"] = _run_variant(
            "tuned_hybrid",
            tuned_embedding,
            tuned_reranker,
            documents,
            tasks,
            fixture,
        )
    language_status = (
        "PASS"
        if census["case_count"] >= MIN_BALANCED_CASES
        and census["language_balance_min_fraction"] >= 0.25
        else "CASE_COUNT_BELOW_TARGET"
    )
    return {
        "schema_version": 1,
        "report_type": "ig_rethink_d0_probe",
        "source": {
            "git_sha": revision,
            "ig01d_split": "dev",
            "ig01d_case_count": len(tasks),
            "ig01d_corpus_fingerprint": _hash(
                "\n".join(path.read_text(encoding="utf-8") for path in files)
            ),
            "holdout_included": False,
            "seed": SEED,
            "noise_count": NOISE_COUNT,
        },
        "d0_1_scope_audit": {
            "status": "PASS",
            "scope_filter": "current_project_plus_global",
            "wrong_project_leakage": {
                name: report["safety"]["wrong_project_leakage"]
                for name, report in variants.items()
            },
        },
        "d0_2_corpus_balance": {
            "ig01b_dev": census,
            "ig01d_retrieval_fixture": {
                "case_count": len(tasks),
                "language_field_present": False,
                "language_distribution": {
                    language: sum(1 for document in documents if _language_bucket(document) == language)
                    for language in LANGUAGES
                },
                "status": "LANGUAGE_METADATA_MISSING",
            },
            "status": language_status,
        },
        "d0_3_tuned_model_spike": {
            "mpnet_status": mpnet_status,
            "tuned_provider": tuned_status,
            "variants_measured": sorted(variants),
            "status": "MEASURED_HYBRID_ONLY_TUNED_UNAVAILABLE" if tuned_embedding is None else "MEASURED",
        },
        "variants": variants,
        "case_ids_hashed": [_hash(task.task_id) for task in tasks],
        "safety": {
            name: report["safety"]
            for name, report in variants.items()
        },
        "verdict": "FIX-FIRST" if tuned_embedding is None or language_status != "PASS" else "D1_READY",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the evaluation-only IG rethink D0 probe")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    result = run_d0_probe()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "output": str(args.output),
        "status": result["verdict"],
        "case_count": result["source"]["ig01d_case_count"],
        "holdout_included": result["source"]["holdout_included"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
