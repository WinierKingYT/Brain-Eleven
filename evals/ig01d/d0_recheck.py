"""D0 recheck: fair-metric rescoring plus a real query-aware lexical hybrid.

This module is evaluation-only, exactly like ``d0_rethink.py`` and
``spike.py`` next to it. It does not modify either file; it imports what it
needs from them and from the read-only ``retrieval_decision_v2.engine``
lexical scorer to run two independent recheck experiments described in
``D0-RECHECK-FINDINGS.md``:

Experiment 1 (fair-metric rescoring): the saved D0 evidence
(``d0-probe-real-exact.json`` / ``d0-probe-real.json``) contains only
aggregate and per-language metrics -- no per-case ranked retrieval lists --
so this module re-runs the same corpus/vault/provider construction
``d0_rethink.py`` uses to regenerate per-case rankings, then recomputes
``precision@5`` (the original metric), ``precision@min(5, |relevant|)``
(the corrected metric), ``recall@5`` and MRR per case from those rankings.

Experiment 2 (real lexical+semantic hybrid): the same semantic ranking is
RRF-fused with a genuinely query-aware lexical ranking produced by
``retrieval_decision_v2.engine._text_scores`` (IDF term-overlap) over the
same scope-filtered candidate pool, instead of ``BaselineContextProvider``
(which never receives ``task.prompt``).

Nothing here writes canonical memory, mutates production retrieval, or
changes ``IG01-A-EVALUATION-CONTRACT.md`` thresholds. Output is aggregate
metrics and hashed case identities only; task/memory text never leaves this
process.
"""

from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path
from typing import Any, Mapping, Sequence

from brain_eleven.retrieval.embedding_provider import EmbeddingProvider, Reranker

from ..baseline import BaselineContextProvider
from ..fixture_generator import build_vault
from .d0_rethink import (
    D0_RETRIEVAL_CORPUS,
    D0_RETRIEVAL_METADATA,
    FIXTURE_PATH,
    NOISE_COUNT,
    ROOT,
    SEED,
    _git_sha,
    _hash,
    _load_versioned_retrieval_cases,
    _rank_semantic,
    _rrf,
    _safety_counts,
    _scope_safe,
)
from .spike import _K, _aggregate, _allowed_records, _language_bucket, _read_records

# retrieval_decision_v2 is read-only-imported here (its _text_scores helper
# only); nothing in this module writes through the engine or touches its
# router/authority machinery.
from retrieval_decision_v2.engine import _text_scores  # noqa: E402


LANGUAGES = ("en", "tr", "tr-en")


def _metric_row_recheck(
    retrieved: Sequence[str],
    required: Sequence[str],
    useful: Sequence[str],
    k: int = _K,
) -> dict[str, float | int | None]:
    """Reproduce spike.py's precision@5/recall@5/MRR and add precision@min(5,|relevant|).

    ``precision_at_5`` and ``recall_at_5``/``mrr`` are computed identically to
    ``spike._metric_row`` (same top-k window, same tie-break-free ranking
    order) so they are directly comparable to the original saved numbers.
    ``precision_at_min5_relevant`` additionally reports standard
    precision@k with k = min(5, |required ∪ useful|) for this case: the top
    k ranked ids are taken and precision is relevant-found / k, which is the
    metric ``D0-RECHECK-FINDINGS.md`` calls for -- a case can never be
    penalized for retrieving 5 slots when fewer than 5 relevant ids exist.
    """

    top = list(retrieved[:k])
    relevant = set(required) | set(useful)
    required_set = set(required)
    relevant_count = sum(item in relevant for item in top)
    required_count = sum(item in required_set for item in top)
    precision_at_5 = relevant_count / len(top) if top else 0.0

    denom = min(k, len(relevant))
    top_corrected = top[:denom] if denom else []
    relevant_in_corrected = sum(item in relevant for item in top_corrected)
    precision_at_min = (relevant_in_corrected / denom) if denom else 0.0

    recall_at_5 = required_count / len(required_set) if required_set else None

    reciprocal_rank = 0.0
    for rank, item in enumerate(top, 1):
        if item in relevant:
            reciprocal_rank = 1.0 / rank
            break
    mrr = reciprocal_rank if relevant else None

    return {
        "precision_at_5": precision_at_5,
        "precision_at_min5_relevant": precision_at_min,
        "recall_at_5": recall_at_5,
        "mrr": mrr,
        "relevant_count": len(relevant),
    }


def _aggregate_recheck(rows: Sequence[Mapping[str, Any]]) -> dict[str, float | None]:
    names = ("precision_at_5", "precision_at_min5_relevant", "recall_at_5", "mrr")
    out: dict[str, float | None] = {}
    for name in names:
        values = [float(row[name]) for row in rows if row.get(name) is not None]
        out[name] = (sum(values) / len(values)) if values else None
    return out


def _lexical_rank(task: Any, candidates: Sequence[Mapping[str, Any]]) -> list[str]:
    """Rank the same scope-filtered candidate pool with a real query-aware
    lexical scorer (IDF term-overlap, ``retrieval_decision_v2.engine._text_scores``),
    instead of the query-blind ``BaselineContextProvider``.
    """

    texts = {
        str(record["memory_id"]): str(record.get("content", ""))
        for record in candidates
    }
    scores, has_query = _text_scores(task.prompt, texts)
    if not has_query:
        # _text_scores degrades to an empty term set for an empty/未知 query;
        # keep a deterministic, content-free fallback ordering rather than
        # silently ranking by insertion order.
        return sorted(texts)
    return sorted(texts, key=lambda memory_id: (-scores.get(memory_id, 0.0), memory_id))


def run_recheck(
    *,
    root: Path = ROOT,
    retrieval_path: Path = D0_RETRIEVAL_CORPUS,
    retrieval_metadata_path: Path = D0_RETRIEVAL_METADATA,
    fixture_path: Path = FIXTURE_PATH,
    embedding_provider: EmbeddingProvider,
    reranker: Reranker,
) -> dict[str, Any]:
    """Regenerate per-case rankings for three variants and score all four metrics.

    Variants:
      - ``semantic_only``: the same semantic ranking d0_rethink.py measured
        as ``mpnet_scope_filtered`` (or whatever provider is passed in).
      - ``hybrid_baseline_blind``: RRF-fused with ``BaselineContextProvider``
        (query-blind), reproducing d0_rethink.py's ``mpnet_hybrid`` control.
      - ``hybrid_lexical_query_aware``: RRF-fused with
        ``retrieval_decision_v2.engine._text_scores`` (query-aware IDF
        term-overlap) over the same candidate pool.

    All three variants share one semantic ranking per case (computed once)
    so differences between them are attributable only to the fusion partner.
    """

    revision = _git_sha(root)
    documents, (fixture, tasks) = _load_versioned_retrieval_cases(
        retrieval_path, retrieval_metadata_path, fixture_path,
    )
    corpus_fingerprint = _hash(retrieval_path.read_text(encoding="utf-8"))

    variant_rows: dict[str, list[dict[str, Any]]] = {
        "semantic_only": [],
        "hybrid_baseline_blind": [],
        "hybrid_lexical_query_aware": [],
    }
    variant_safety: dict[str, Any] = {name: {} for name in variant_rows}
    from collections import Counter

    safety_counters = {name: Counter() for name in variant_rows}
    provider_identity: dict[str, Any] = {}
    baseline = BaselineContextProvider()

    with tempfile.TemporaryDirectory(prefix="brain-eleven-d0-recheck-") as directory:
        vault = build_vault(fixture, Path(directory) / "vault", seed=SEED, noise_count=NOISE_COUNT)
        records = _read_records(vault.root)
        for document, task in zip(documents, tasks):
            candidates = _allowed_records(records, task.project_id)
            semantic_ids, identity = _rank_semantic(
                task=task,
                records=records,
                embedding_provider=embedding_provider,
                reranker=reranker,
            )
            provider_identity = identity

            baseline_selection = baseline.select(task, vault.root)
            baseline_ids = [str(item.id) for item in baseline_selection.selected_items]
            hybrid_blind_ids = _rrf(semantic_ids, baseline_ids)

            lexical_ids = _lexical_rank(task, candidates)
            hybrid_lexical_ids = _rrf(semantic_ids, lexical_ids)

            required = tuple(document["expected_context"]["required"])
            useful = tuple(document["expected_context"]["useful"])
            forbidden = set(document["expected_context"]["forbidden"])
            language = _language_bucket(document)

            for name, selected_ids in (
                ("semantic_only", semantic_ids),
                ("hybrid_baseline_blind", hybrid_blind_ids),
                ("hybrid_lexical_query_aware", hybrid_lexical_ids),
            ):
                metrics = _metric_row_recheck(selected_ids, required, useful)
                variant_rows[name].append({
                    "task_id": task.task_id,
                    "language": language,
                    **metrics,
                })
                safety_counters[name].update(
                    _safety_counts(selected_ids, records, task, forbidden)
                )

    variants_out: dict[str, Any] = {}
    for name, rows in variant_rows.items():
        per_language = {}
        for language in LANGUAGES:
            subset = [row for row in rows if row["language"] == language]
            per_language[language] = {
                "case_count": len(subset),
                "metrics": _aggregate_recheck(subset),
            }
        variants_out[name] = {
            "case_count": len(rows),
            "metrics": _aggregate_recheck(rows),
            "per_language": per_language,
            "safety": dict(sorted(safety_counters[name].items())),
        }

    oracle_scores = [
        min(len(set(document["expected_context"]["required"]) | set(document["expected_context"]["useful"])), _K) / _K
        for document in documents
    ]
    oracle_precision_at_5 = sum(oracle_scores) / len(oracle_scores) if oracle_scores else None

    return {
        "schema_version": 1,
        "report_type": "ig_d0_recheck",
        "source": {
            "git_sha": revision,
            "ig01d_split": "ig-r3-d0-v1",
            "ig01d_case_count": len(tasks),
            "ig01d_corpus_fingerprint": corpus_fingerprint,
            "holdout_included": False,
            "seed": SEED,
            "noise_count": NOISE_COUNT,
            "k": _K,
        },
        "provider_identity": provider_identity,
        "oracle_precision_at_5": oracle_precision_at_5,
        "variants": variants_out,
        "case_ids_hashed": [_hash(task.task_id) for task in tasks],
        "production_mutation": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the evaluation-only IG D0 recheck probe")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--embedding-model",
        default="sentence-transformers/paraphrase-multilingual-mpnet-base-v2",
    )
    parser.add_argument(
        "--reranker-model",
        default="cross-encoder/mmarco-mMiniLMv2-L12-H384-v1",
    )
    parser.add_argument("--e5-prefix", action="store_true", help="apply the E5 query:/passage: prefix contract")
    parser.add_argument(
        "--local-files-only",
        action="store_true",
        help="require the model to already be cached locally (matches d0_rethink.py's production-safety default)",
    )
    args = parser.parse_args(argv)

    from brain_eleven.retrieval.embedding_provider import LocalCrossEncoderReranker, LocalSentenceTransformerProvider
    from .d0_rethink import _E5PrefixedProvider

    embedding: EmbeddingProvider = LocalSentenceTransformerProvider(
        args.embedding_model, local_files_only=args.local_files_only,
    )
    if args.e5_prefix:
        embedding = _E5PrefixedProvider(embedding)
    reranker: Reranker = LocalCrossEncoderReranker(
        args.reranker_model, local_files_only=args.local_files_only,
    )

    result = run_recheck(embedding_provider=embedding, reranker=reranker)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "output": str(args.output),
        "case_count": result["source"]["ig01d_case_count"],
        "oracle_precision_at_5": result["oracle_precision_at_5"],
        "semantic_only_precision_at_5": result["variants"]["semantic_only"]["metrics"]["precision_at_5"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
