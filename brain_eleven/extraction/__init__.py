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

__all__ = [
    "EntityExtractor",
    "PHASE_PATTERN",
    "ProjectionInvariantError",
    "TECH_LEXICON",
]
