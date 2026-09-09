"""Throwaway semantic ceiling probe for IG01-D.

This module is deliberately provider-agnostic and never runs in a production
retrieval path.  It records an explicit unavailable result when a real
embedding and cross-encoder provider cannot be imported; deterministic/hash
vectors are never treated as a semantic ceiling.
"""

from __future__ import annotations

import importlib.util
import time
from pathlib import Path
from typing import Any

from brain_eleven.retrieval.embedding_provider import EmbeddingProvider, create_embedding_provider

from .fingerprint import corpus_split_fingerprint


def _provider_status() -> tuple[str, str]:
    if importlib.util.find_spec("sentence_transformers") is not None:
        return "sentence_transformers", "local embedding/cross-encoder package detected"
    if importlib.util.find_spec("openai") is not None:
        return "openai_only", "embedding client detected but no cross-encoder provider is installed"
    return "none", "no real embedding or cross-encoder provider is installed"


def configured_embedding_provider() -> EmbeddingProvider:
    """Return the config-gated embedding socket without running a probe."""

    return create_embedding_provider()


def run_feasibility_probe(
    *,
    root: Path | str,
    corpus_root: Path | str,
    fixture_path: Path | str,
    git_sha: str,
    dev_case_count: int = 50,
    embedding_provider: EmbeddingProvider | None = None,
) -> dict[str, Any]:
    """Probe only the first 50 DEV cases and never touch HOLDOUT."""

    del root, fixture_path, git_sha  # Inputs are retained in the output contract by the caller.
    if dev_case_count != 50:
        raise ValueError("IG01-D feasibility probe is fixed at 50 DEV cases")
    dev_root = Path(corpus_root).resolve() / "dev"
    files = sorted(dev_root.glob("p15_*.json"))
    if len(files) < dev_case_count:
        raise ValueError("IG01-D DEV corpus has fewer than 50 cases")
    selected_embedding = embedding_provider or configured_embedding_provider()
    provider_id, reason = _provider_status()
    if selected_embedding.provider_id != "unavailable":
        provider_id = selected_embedding.provider_id
        reason = "embedding provider selected; cross-encoder provider is not configured"
    started = time.perf_counter()
    # The spike stays conservative until both a real embedding and a real
    # cross-encoder are available. Returning unavailable is evidence, not a
    # fabricated score from hash vectors or the production heuristic.
    status = "SEMANTIC_UNAVAILABLE"
    precision = None
    ceiling = None
    if provider_id == "sentence_transformers":
        reason = "provider detected; throwaway cross-encoder wiring is not part of production IG01-D"
    return {
        "status": status,
        "provider_id": provider_id,
        "reason": reason,
        "case_count": dev_case_count,
        "split": "dev",
        "holdout_included": False,
        "corpus_split_fingerprint": corpus_split_fingerprint(Path(corpus_root)),
        "precision": precision,
        "empirical_ceiling": ceiling,
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
        "measurement": "no score without a real embedding plus cross-encoder pair",
    }

