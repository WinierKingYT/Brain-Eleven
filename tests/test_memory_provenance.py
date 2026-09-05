"""PRE-05 legacy temporal/provenance projection tests."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from memory_provenance import MemoryProvenanceStore, ProvenanceCorruptError


def _memory_store(vault):
    source = Path(__file__).parent.parent / "scripts" / "memory_store.py"
    spec = importlib.util.spec_from_file_location("memory_store_for_provenance", source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.MemoryStore(vault)


def test_migration_preserves_ids_revision_and_distinguishes_daily_day_from_capture_time(tmp_path):
    vault = tmp_path / "vault"
    store = _memory_store(vault)
    source = {
        "schema_version": 2,
        "revision": 7,
        "validated_memory": [
            {
                "memory_id": "mem_daily",
                "source_id": "daily:2026-08-28:decision:0",
                "timestamp": "2026-09-04T10:00:00",
                "content": "SQLite is local persistence.",
                "type": "decision",
                "status": "active",
            }
        ],
        "rejected_memory": [],
    }
    store.path.parent.mkdir(parents=True, exist_ok=True)
    store.path.write_text(json.dumps(source), encoding="utf-8")

    result = MemoryProvenanceStore(vault).migrate_legacy()
    record = result["records"]["mem_daily"]

    assert result["source_memory_revision"] == 7
    assert record["occurred_at"] == {"value": "2026-08-28", "precision": "day"}
    assert record["captured_at"] == {"value": "2026-09-04T10:00:00", "precision": "unknown"}
    assert record["canonicalized_at"] is None
    assert json.loads(store.path.read_text(encoding="utf-8"))["revision"] == 7


def test_migration_is_repeatable_and_corrupt_projection_fails_closed(tmp_path):
    vault = tmp_path / "vault"
    store = _memory_store(vault)
    store.path.parent.mkdir(parents=True, exist_ok=True)
    store.path.write_text(json.dumps({"schema_version": 2, "revision": 1, "validated_memory": [], "rejected_memory": []}), encoding="utf-8")
    projection = MemoryProvenanceStore(vault)
    first = projection.migrate_legacy()
    second = projection.migrate_legacy()
    assert first["records"] == second["records"] == {}
    assert first["updated_at"] == second["updated_at"]

    projection.path.write_text(json.dumps({"schema_version": 1, "source_memory_revision": 1, "records": {"wrong": {"memory_id": "other"}}}), encoding="utf-8")
    with pytest.raises(ProvenanceCorruptError):
        projection.load()
