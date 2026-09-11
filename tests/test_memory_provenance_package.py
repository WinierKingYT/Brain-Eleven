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
import memory_provenance as legacy


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


def test_package_and_all_legacy_surfaces_preserve_object_identity() -> None:
    assert memory_package.MemoryProvenanceStore is package.MemoryProvenanceStore
    assert memory_package.MemoryProvenance is package.MemoryProvenance
    assert legacy.MemoryProvenanceStore is package.MemoryProvenanceStore
    assert legacy.MemoryProvenance is package.MemoryProvenance
    assert legacy.ProvenanceCorruptError is package.ProvenanceCorruptError
    assert legacy.ProvenanceStoreError is package.ProvenanceStoreError
    assert legacy.provenance_path is package.provenance_path
    assert legacy.main is package.main


def test_legacy_script_is_an_adapter_without_provenance_implementation() -> None:
    source = (ROOT / "scripts" / "memory_provenance.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    defined_classes = {node.name for node in ast.walk(tree) if isinstance(node, ast.ClassDef)}
    defined_functions = {node.name for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}

    assert defined_classes == set()
    assert defined_functions == {"_load_canonical"}
    assert "from brain_eleven.memory" in source
    assert "brain_eleven.memory.provenance" in source
    assert "canonical memory is missing memory_id" not in source


def test_package_and_legacy_cli_paths_produce_equivalent_projection(tmp_path: Path) -> None:
    package_vault = tmp_path / "package"
    legacy_vault = tmp_path / "legacy"
    package_memory = _write_canonical(package_vault)
    legacy_memory = _write_canonical(legacy_vault)

    package_result = package.MemoryProvenanceStore(package_vault).migrate_legacy()
    legacy_result = legacy.MemoryProvenanceStore(legacy_vault).migrate_legacy()

    assert {key: package_result[key] for key in ("schema_version", "source_memory_revision", "records")} == {
        key: legacy_result[key] for key in ("schema_version", "source_memory_revision", "records")
    }
    assert json.loads(package_memory.read_text(encoding="utf-8"))["revision"] == 7
    assert json.loads(legacy_memory.read_text(encoding="utf-8"))["revision"] == 7


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


@pytest.mark.parametrize("store_type", [package.MemoryProvenanceStore, legacy.MemoryProvenanceStore])
def test_lock_failure_has_same_projection_error_code(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, store_type) -> None:
    vault = tmp_path / store_type.__module__.replace(".", "_")
    _write_canonical(vault)
    monkeypatch.setattr(package, "file_lock", _timed_out_lock)

    with pytest.raises(package.ProvenanceStoreError) as error:
        store_type(vault).migrate_legacy()
    assert error.value.code == "MEMORY_PROVENANCE_WRITE_FAILED"


def test_direct_legacy_cli_emits_bounded_receipt(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    _write_canonical(vault, revision=11)
    command = [sys.executable, str(ROOT / "scripts" / "memory_provenance.py"), "--vault", str(vault)]
    kwargs = {"capture_output": True, "text": True, "check": False}
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    result = subprocess.run(command, **kwargs)

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload == {"record_count": 1, "source_memory_revision": 11}
