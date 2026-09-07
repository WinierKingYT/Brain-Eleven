from __future__ import annotations

import pytest

from evals.intelligence_taxonomy import METRICS, TAXONOMY, TAXONOMY_VERSION, taxonomy_manifest, validate_category


def test_taxonomy_is_versioned_and_serializable():
    manifest = taxonomy_manifest()

    assert manifest["version"] == TAXONOMY_VERSION
    assert set(manifest["families"]) == {"retrieval", "extraction", "reference_resolution", "safety"}
    assert manifest["families"]["retrieval"]
    assert manifest["metrics"]["retrieval"] == list(METRICS["retrieval"])


def test_taxonomy_categories_are_unique_across_each_family():
    for categories in TAXONOMY.values():
        assert len(categories) == len(set(categories))


def test_unknown_taxonomy_categories_fail_closed():
    validate_category("retrieval", "old_critical_decision")

    with pytest.raises(ValueError, match="unknown"):
        validate_category("retrieval", "select_everything")
