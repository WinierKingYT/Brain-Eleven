"""Parity checks for the first PRE-12 repository consolidation boundary."""

from __future__ import annotations

import json

from brain_eleven.projects import registry as package_registry


def test_project_registry_package_surface_is_legacy_parity():
    import project_registry as legacy_registry

    assert package_registry.ProjectRegistry is legacy_registry.ProjectRegistry
    assert package_registry.ProjectRegistryError is legacy_registry.ProjectRegistryError
    assert package_registry.REGISTRY_SCHEMA_VERSION == legacy_registry.REGISTRY_SCHEMA_VERSION
    assert package_registry.VALID_STATUSES == legacy_registry.VALID_STATUSES


def test_project_registry_package_surface_preserves_behavior(tmp_path):
    registry = package_registry.ProjectRegistry(tmp_path)
    record = registry.register(tmp_path / "project", project_id="proj_parity")

    assert record["project_id"] == "proj_parity"
    assert registry.get("proj_parity")["root"] == record["root"]
    persisted = json.loads(registry.path.read_text(encoding="utf-8"))
    assert persisted["schema_version"] == package_registry.REGISTRY_SCHEMA_VERSION
    assert persisted["projects"][0]["project_id"] == "proj_parity"
