"""IG-07 Slice 2C C3 package authority and rollback safety tests."""

from __future__ import annotations

import ast
import importlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest

from brain_eleven.memory import MemoryStore, MemoryStoreConflict


ROOT = Path(__file__).resolve().parents[1]
ADAPTER_PATH = ROOT / "scripts" / "migrate-memory-scope.py"


def _load_adapter():
    spec = importlib.util.spec_from_file_location("memory_scope_migration", ADAPTER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _write_source(vault: Path) -> tuple[Path, dict]:
    path = vault / ".claude" / "validated-memory.json"
    source = {
        "revision": 0,
        "validated_memory": [{
            "memory_id": "stable-id",
            "type": "decision",
            "content": "Legacy project decision",
            "project": "Legacy Project",
        }],
        "rejected_memory": [],
    }
    path.write_text(json.dumps(source, indent=2), encoding="utf-8")
    return path, source


@pytest.fixture
def vault(tmp_path: Path) -> Path:
    target = tmp_path / "vault"
    (target / ".claude").mkdir(parents=True)
    return target


def test_package_adapter_and_bare_module_preserve_identity() -> None:
    adapter = _load_adapter()
    canonical = importlib.import_module("brain_eleven.memory.migrations")
    bare = sys.modules["memory_scope_migration"]

    assert adapter.migrate_scope is canonical.migrate_scope
    assert adapter.rollback_scope is canonical.rollback_scope
    assert adapter.migrate is canonical.migrate_scope
    assert adapter.rollback is canonical.rollback_scope
    assert bare.migrate_scope is canonical.migrate_scope
    assert adapter.SCOPE_MIGRATION_NAME is canonical.SCOPE_MIGRATION_NAME
    assert adapter.MemoryScopeMigrationError is canonical.MemoryScopeMigrationError


def test_adapter_contains_no_scope_implementation() -> None:
    source = ADAPTER_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    definitions = [
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
    ]
    assert definitions == ["_load_canonical"]
    assert "def migrate(" not in source
    assert "def rollback(" not in source
    assert "MemoryStore(" not in source


def test_scope_migration_is_idempotent_without_revision_change(vault: Path) -> None:
    path, _source = _write_source(vault)
    migration = importlib.import_module("brain_eleven.memory.migrations")

    first = migration.migrate_scope(vault)
    first_document = MemoryStore(vault).load()
    second = migration.migrate_scope(vault)

    assert first["status"] == "migrated"
    assert second["status"] == "unchanged"
    assert second["revision"] == first["revision"]
    assert json.loads(path.read_text(encoding="utf-8"))["revision"] == first_document["revision"]


def test_rollback_restores_payload_and_is_guarded_on_replay(vault: Path) -> None:
    path, source = _write_source(vault)
    migration = importlib.import_module("brain_eleven.memory.migrations")

    migrated = migration.migrate_scope(vault)
    migrated_document = MemoryStore(vault).load()
    rollback = migration.rollback_scope(vault, migrated["backup"])
    restored = json.loads(path.read_text(encoding="utf-8"))

    assert rollback["status"] == "rolled_back"
    assert rollback["revision"] > migrated_document["revision"]
    assert rollback["revision"] >= 2
    assert restored["validated_memory"] == source["validated_memory"]
    assert restored["rejected_memory"] == source["rejected_memory"]
    assert restored["validated_memory"][0]["memory_id"] == "stable-id"

    replay = migration.rollback_scope(vault, migrated["backup"])
    assert replay["status"] == "already_rolled_back"
    assert replay["revision"] == rollback["revision"]
    assert MemoryStore(vault).revision() == rollback["revision"]


def test_rollback_uses_cas_and_rejects_concurrent_writer(vault: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _path, _source = _write_source(vault)
    migration = importlib.import_module("brain_eleven.memory.migrations")
    migrated = migration.migrate_scope(vault)
    original_replace = MemoryStore.replace
    injected = {"done": False}

    def racing_replace(store, data, expected_revision=None):
        if expected_revision is not None and not injected["done"]:
            injected["done"] = True
            store.append({
                "memory_id": "concurrent",
                "type": "observation",
                "content": "concurrent writer",
            })
        return original_replace(store, data, expected_revision=expected_revision)

    monkeypatch.setattr(MemoryStore, "replace", racing_replace)
    with pytest.raises(MemoryStoreConflict):
        migration.rollback_scope(vault, migrated["backup"])

    current = MemoryStore(vault).load()
    assert {item["memory_id"] for item in current["validated_memory"]} == {
        "stable-id", "concurrent"
    }


def test_invalid_missing_and_corrupt_backups_fail_without_replacement(vault: Path) -> None:
    path, _source = _write_source(vault)
    migration = importlib.import_module("brain_eleven.memory.migrations")
    before = path.read_bytes()
    missing = vault / "missing.bak"
    corrupt = vault / "corrupt.bak"
    corrupt.write_text("{not json", encoding="utf-8")

    for backup in (missing, corrupt):
        with pytest.raises(migration.MemoryScopeMigrationError):
            migration.rollback_scope(vault, backup)
        assert path.read_bytes() == before


def test_dry_run_has_no_canonical_effect(vault: Path) -> None:
    path, _source = _write_source(vault)
    migration = importlib.import_module("brain_eleven.memory.migrations")
    before = path.read_bytes()

    result = migration.migrate_scope(vault, dry_run=True)

    assert result["status"] == "dry_run"
    assert path.read_bytes() == before
    assert not list(path.parent.glob("*.pre-scope-v2-*.bak"))
