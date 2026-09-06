"""Public boundary for deterministic entity extraction.

The legacy implementation remains in ``scripts/entity_extractor.py`` while
repository consolidation proceeds incrementally.  This package re-exports
the exact implementation objects so callers share one extractor and existing
graph projection behavior remains unchanged.
"""

from __future__ import annotations

import sys
from pathlib import Path


_ROOT = Path(__file__).resolve().parents[2]
_SCRIPTS = _ROOT / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from entity_extractor import (  # noqa: E402
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
