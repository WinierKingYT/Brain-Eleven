"""D0 BGE-M3 measurement: actually run the candidate `d0_rethink.py` never measured.

``evals/ig01d/d0_rethink.py``'s ``_try_tuned_provider`` lists
``("BAAI/bge-m3", "BAAI/bge-reranker-v2-m3", False)`` as a second tuned-model
candidate alongside ``intfloat/multilingual-e5-large``, but the loop returns
as soon as the first candidate (E5-large) succeeds, so BGE-M3 was never
actually run against this corpus. This module closes that gap.

This is evaluation-only, exactly like ``d0_recheck.py`` next to it, and does
not modify ``d0_rethink.py``, ``spike.py``, or ``d0_recheck.py`` -- it only
imports ``run_recheck`` (and, transitively, ``_metric_row_recheck``) from
``d0_recheck.py`` and points it at a BGE-M3 ``LocalSentenceTransformerProvider``
+ BGE-reranker-v2-m3 ``LocalCrossEncoderReranker`` pair, the same construction
``_try_tuned_provider`` already uses for its BGE-M3 candidate. No RRF/fusion
logic, no metric logic, and no corpus/vault construction is reimplemented
here.

BGE-M3 is architecturally a dense+sparse+ColBERT multi-vector retrieval
model. Only its dense embedding output is measured here (the mode
``sentence_transformers.SentenceTransformer.encode()`` returns and the mode
directly comparable to what the MPNet/E5-large providers produce via the
same ``LocalSentenceTransformerProvider`` adapter). The sparse and
multi-vector (ColBERT) modes require the separate ``FlagEmbedding`` package
and a different scoring path (lexical-weight / MaxSim, not cosine similarity)
that ``_rank_semantic`` (``spike.py``) does not implement; wiring that up
would be new retrieval-scoring infrastructure, not a cheap swap-in, so it is
out of scope here per the task's own instruction ("don't attempt the
sparse/multi-vector modes unless they're trivial ... stick to dense
embeddings and note the limitation"). See ``D0-BGE-M3-RESULTS.md`` section 0.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from brain_eleven.retrieval.embedding_provider import (
    EmbeddingProvider,
    LocalCrossEncoderReranker,
    LocalSentenceTransformerProvider,
    Reranker,
)

from .d0_recheck import run_recheck

BGE_M3_EMBEDDING_MODEL = "BAAI/bge-m3"
BGE_M3_RERANKER_MODEL = "BAAI/bge-reranker-v2-m3"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Measure BAAI/bge-m3 (dense embedding mode) against the same "
            "ig-r3-d0-v1 corpus/vault/seed d0_recheck.py used, filling in "
            "the D0 candidate d0_rethink.py's _try_tuned_provider never "
            "actually ran."
        )
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--embedding-model", default=BGE_M3_EMBEDDING_MODEL)
    parser.add_argument("--reranker-model", default=BGE_M3_RERANKER_MODEL)
    parser.add_argument(
        "--local-files-only",
        action="store_true",
        help="require the model to already be cached locally (matches d0_rethink.py's production-safety default)",
    )
    args = parser.parse_args(argv)

    embedding: EmbeddingProvider = LocalSentenceTransformerProvider(
        args.embedding_model, local_files_only=args.local_files_only,
    )
    reranker: Reranker = LocalCrossEncoderReranker(
        args.reranker_model, local_files_only=args.local_files_only,
    )

    result: dict[str, Any] = run_recheck(embedding_provider=embedding, reranker=reranker)
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
        "semantic_only_precision_at_min5_relevant": result["variants"]["semantic_only"]["metrics"]["precision_at_min5_relevant"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
