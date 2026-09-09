"""IG-01-B corpus and ground-truth integrity helpers.

This package owns only the versioned evaluation data contract and its integrity
checks.  It deliberately does not import retrieval, extraction, ranking, or
production memory code.
"""

from .schema import (
    CASE_KINDS,
    DATASET_CLASSES,
    LANGUAGES,
    PHENOMENA,
    SPLITS,
    load_cases,
    validate_case,
)

__all__ = [
    "CASE_KINDS",
    "DATASET_CLASSES",
    "LANGUAGES",
    "PHENOMENA",
    "SPLITS",
    "load_cases",
    "validate_case",
]
