"""Public boundary for deterministic and semantic extraction.

The deterministic entity implementation is canonical in ``.entities``.
``scripts.entity_extractor`` remains a compatibility/direct-execution adapter;
semantic extraction stays proposal-only in ``.semantic``.
"""

from __future__ import annotations

from .entities import (
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
