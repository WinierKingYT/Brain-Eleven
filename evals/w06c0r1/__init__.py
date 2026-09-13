"""W-06C0R1 answerability, provenance and provider-parity evaluator."""

from .evaluation import (
    CORPUS_VERSION,
    EVALUATOR_VERSION,
    K_VALUES,
    PROVIDER_SLOTS,
    W06C0R1Error,
    load_corpus,
    run_matrix,
    source_fingerprint,
    task_set_fingerprint,
    verify_manifest,
    verify_scope_diff,
)

__all__ = [
    "CORPUS_VERSION",
    "EVALUATOR_VERSION",
    "K_VALUES",
    "PROVIDER_SLOTS",
    "W06C0R1Error",
    "load_corpus",
    "run_matrix",
    "source_fingerprint",
    "task_set_fingerprint",
    "verify_manifest",
    "verify_scope_diff",
]
