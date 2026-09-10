"""Public boundary for deterministic entity extraction.

The legacy implementation remains in ``scripts/entity_extractor.py`` while
repository consolidation proceeds incrementally.  This package re-exports
the exact implementation objects so callers share one extractor and existing
graph projection behavior remains unchanged.
"""

from __future__ import annotations

from scripts.entity_extractor import (
    PHASE_PATTERN,
    TECH_LEXICON,
    EntityExtractor,
    ProjectionInvariantError,
)
from .semantic import (  # noqa: E402
    CallableSemanticProvider,
    DeterministicRegexProvider,
    DeterministicSafetyPrefilter,
    PrefilterResult,
    PropositionValidationError,
    ProviderResult,
    SemanticProposition,
    SemanticProvider,
    SemanticStatus,
    UnavailableProvider,
    ValidationResult,
    build_proposition,
    extract_with_provider,
    require_valid_proposition,
    validate_proposition,
)

__all__ = [
    "EntityExtractor",
    "PHASE_PATTERN",
    "ProjectionInvariantError",
    "TECH_LEXICON",
    "CallableSemanticProvider",
    "DeterministicRegexProvider",
    "DeterministicSafetyPrefilter",
    "PrefilterResult",
    "PropositionValidationError",
    "ProviderResult",
    "SemanticProposition",
    "SemanticProvider",
    "SemanticStatus",
    "UnavailableProvider",
    "ValidationResult",
    "build_proposition",
    "extract_with_provider",
    "require_valid_proposition",
    "validate_proposition",
]
