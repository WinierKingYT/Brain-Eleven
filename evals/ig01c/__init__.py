"""IG01-C deterministic evaluation engine.

The package is deliberately production-independent.  It consumes immutable
case labels and normalized system outputs, then emits content-free metrics and
hard-gate evidence.  It never imports a retriever, extractor, model provider,
or canonical persistence authority.
"""

from .contracts import (
    EVALUATOR_VERSION,
    HARD_ZERO_GATES,
    NEAR_ZERO_GATES,
    EvaluationContractError,
    MetricValue,
    SafetyEvent,
)
from .engine import (
    EvaluatorError,
    evaluate_case,
    evaluate_corpus,
    read_report,
    validate_report,
    write_report,
)
from .metrics import (
    evaluate_capture_case,
    evaluate_context_case,
    evaluate_extraction_case,
    evaluate_lifecycle_case,
    evaluate_reference_case,
    evaluate_retrieval_case,
    expected_calibration_error,
    aggregate_metric_values,
    f1_score,
    mandatory_recall,
    mean_reciprocal_rank,
    noise_ratio,
    precision_at_k,
    recall_at_k,
    token_waste,
)

__all__ = [
    "EVALUATOR_VERSION",
    "HARD_ZERO_GATES",
    "NEAR_ZERO_GATES",
    "EvaluationContractError",
    "EvaluatorError",
    "MetricValue",
    "SafetyEvent",
    "evaluate_case",
    "evaluate_capture_case",
    "evaluate_context_case",
    "evaluate_corpus",
    "evaluate_extraction_case",
    "evaluate_lifecycle_case",
    "evaluate_reference_case",
    "evaluate_retrieval_case",
    "expected_calibration_error",
    "aggregate_metric_values",
    "f1_score",
    "mandatory_recall",
    "mean_reciprocal_rank",
    "noise_ratio",
    "precision_at_k",
    "recall_at_k",
    "token_waste",
    "read_report",
    "validate_report",
    "write_report",
]
