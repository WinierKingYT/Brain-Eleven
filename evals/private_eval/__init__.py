"""Local-only real-use evaluation and derived usage feedback contracts.

The implementation is versioned in the repository, while real cases and
reports belong under the ignored ``evals/private/`` directory.  No API in
this package accepts or persists task prose, memory content, or transcripts.
"""

from .contracts import (
    ANNOTATION_LABELS,
    PRIVATE_EVAL_SCHEMA_VERSION,
    PrivateEvaluationCase,
    PrivateEvaluationError,
    evaluate_case,
    load_case,
    write_case,
)
from .usage import (
    USAGE_EVENTS,
    UsageTelemetryError,
    UsageTelemetryStore,
)

__all__ = [
    "ANNOTATION_LABELS",
    "PRIVATE_EVAL_SCHEMA_VERSION",
    "PrivateEvaluationCase",
    "PrivateEvaluationError",
    "USAGE_EVENTS",
    "UsageTelemetryError",
    "UsageTelemetryStore",
    "evaluate_case",
    "load_case",
    "write_case",
]
