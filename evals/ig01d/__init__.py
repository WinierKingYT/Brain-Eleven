"""IG01-D baseline measurement package.

The package is an evaluation adapter only.  It runs the existing V1 and V2
providers against one frozen public corpus and emits content-free, revision
bound evidence.  It does not tune retrieval, change production providers, or
promote the shadow compiler.
"""

from .contracts import BaselineContractError
from .fingerprint import corpus_split_fingerprint, evaluation_source_fingerprint
from .spike import run_feasibility_probe


def __getattr__(name):
    """Keep contract/fingerprint imports usable without runtime dependencies."""

    if name in {
        "CORPUS_VERSION", "DEFAULT_CORPUS_ROOT", "DEFAULT_FIXTURE_PATH",
        "EVALUATOR_VERSION", "IG01D_SCHEMA_VERSION", "NOISE_COUNT", "SEED",
        "build_pair_report", "read_pair_report", "validate_pair_report", "write_pair_report",
    }:
        from . import baseline

        return getattr(baseline, name)
    raise AttributeError(name)

__all__ = [
    "BaselineContractError",
    "CORPUS_VERSION",
    "DEFAULT_CORPUS_ROOT",
    "DEFAULT_FIXTURE_PATH",
    "EVALUATOR_VERSION",
    "IG01D_SCHEMA_VERSION",
    "NOISE_COUNT",
    "SEED",
    "build_pair_report",
    "corpus_split_fingerprint",
    "evaluation_source_fingerprint",
    "read_pair_report",
    "run_feasibility_probe",
    "validate_pair_report",
    "write_pair_report",
]
