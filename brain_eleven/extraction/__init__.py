"""Public boundary for deterministic entity extraction.

The entity implementation remains in ``scripts/entity_extractor.py`` until
Slice 2B Step B2.2. The graph projection it consumes is already canonical in
``brain_eleven.graph.projection``; re-exporting the current entity objects
keeps callers on one extractor while that second inversion is pending.
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
