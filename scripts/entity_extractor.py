#!/usr/bin/env python3
"""Compatibility/direct-execution adapter for canonical entity extraction."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from types import ModuleType


_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    # Historical direct execution starts with ``scripts/`` on sys.path.
    sys.path.insert(0, str(_ROOT))


def _load_canonical(name: str, path: Path) -> ModuleType:
    """Load and cache the package implementation for the legacy entrypoint."""

    existing = sys.modules.get(name)
    if existing is not None:
        return existing
    if not path.is_file():
        raise ImportError(f"Cannot load canonical module: {path}")
    module = importlib.import_module(name)
    sys.modules.setdefault(name, module)
    return module


_entities = _load_canonical(
    "brain_eleven.extraction.entities",
    _ROOT / "brain_eleven" / "extraction" / "entities.py",
)

TECH_LEXICON = _entities.TECH_LEXICON
PHASE_PATTERN = _entities.PHASE_PATTERN
ProjectionInvariantError = _entities.ProjectionInvariantError
EntityExtractor = _entities.EntityExtractor
_slugify = _entities._slugify
main = _entities.main
logger = _entities.logger

__all__ = [
    "TECH_LEXICON",
    "PHASE_PATTERN",
    "ProjectionInvariantError",
    "EntityExtractor",
    "_slugify",
    "main",
    "logger",
]


# Preserve the historical bare module name used by direct imports and pytest.
# The alias points at the canonical module so monkeypatching and class identity
# remain consistent across all four supported import surfaces.
if __name__ == "scripts.entity_extractor":
    sys.modules.setdefault("entity_extractor", _entities)


if __name__ == "__main__":
    raise SystemExit(main())
