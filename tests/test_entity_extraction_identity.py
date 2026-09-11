"""IG-07 Slice 2B B2.2 identity contract tests."""

from __future__ import annotations

import importlib


def test_entity_extraction_public_surfaces_share_canonical_objects() -> None:
    package = importlib.import_module("brain_eleven.extraction")
    canonical = importlib.import_module("brain_eleven.extraction.entities")
    adapter = importlib.import_module("scripts.entity_extractor")
    bare = importlib.import_module("entity_extractor")

    for name in (
        "EntityExtractor",
        "ProjectionInvariantError",
        "TECH_LEXICON",
        "PHASE_PATTERN",
    ):
        expected = getattr(canonical, name)
        assert getattr(package, name) is expected
        assert getattr(adapter, name) is expected
        assert getattr(bare, name) is expected

    assert adapter._slugify is canonical._slugify
    assert adapter.logger is canonical.logger
