"""IG-07 Slice 2A contract tests for the canonical provenance package."""

from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path

import pytest

import brain_eleven.memory as memory_package
import brain_eleven.memory.provenance as package


ROOT = Path(__file__).resolve().parents[1]


def _write_canonical(vault: Path, *, revision: int = 7, memory_id: str = "mem_daily") -> Path:
    path = vault / ".claude" / "validated-memory.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "revision": revision,
                "validated_memory": [
                    {
                        "memory_id": memory_id,
                        "source_id": "daily:2026-08-28:decision:0",
                        "timestamp": "2026-09-04T10:00:00",
                        "content": "SQLite is local persistence.",
                        "type": "decision",
                        "status": "active",
                    }
                ],
                "rejected_memory": [],
            }
        ),
        encoding="utf-8",
    )
    return path


def test_revision_bound_projection_updates_without_changing_canonical_revision(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    canonical_path = _write_canonical(vault, revision=3)
    projection = package.MemoryProvenanceStore(vault)

    first = projection.migrate_legacy()
    assert first["source_memory_revision"] == 3
    assert json.loads(canonical_path.read_text(encoding="utf-8"))["revision"] == 3

    canonical = json.loads(canonical_path.read_text(encoding="utf-8"))
    canonical["revision"] = 4
    canonical_path.write_text(json.dumps(canonical), encoding="utf-8")
    second = projection.migrate_legacy()
    assert second["source_memory_revision"] == 4
    assert json.loads(canonical_path.read_text(encoding="utf-8"))["revision"] == 4


@contextmanager
def _timed_out_lock(*_args, **_kwargs):
    raise package.MemoryStoreLockTimeout("test lock timeout")
    yield


def test_lock_failure_has_same_projection_error_code(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    vault = tmp_path / "vault"
    _write_canonical(vault)
    monkeypatch.setattr(package, "file_lock", _timed_out_lock)

    with pytest.raises(package.ProvenanceStoreError) as error:
        package.MemoryProvenanceStore(vault).migrate_legacy()
    assert error.value.code == "MEMORY_PROVENANCE_WRITE_FAILED"


