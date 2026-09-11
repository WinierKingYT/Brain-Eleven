"""IG-07 Slice 2C C1 dedupe migration and safety contract tests."""

from __future__ import annotations

import ast
import importlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest

from brain_eleven.lifecycle import MemoryLifecycleManager, plan_dedupe
from brain_eleven.memory import MemoryStore, MemoryStoreConflict


ROOT = Path(__file__).resolve().parents[1]
ADAPTER_PATH = ROOT / "scripts" / "dedupe-validated-memory.py"


def _load_adapter():
    spec = importlib.util.spec_from_file_location("dedupe_validated_memory", ADAPTER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _memory(memory_id: str, timestamp: str, *, status: str = "active") -> dict:
    return {
        "memory_id": memory_id,
        "type": "decision",
        "content": f"duplicate {memory_id}",
        "timestamp": timestamp,
        "dedup_fingerprint": "fp-shared",
        "status": status,
    }


def _seed_vault(tmp_path: Path, memories: list[dict]) -> Path:
    vault = tmp_path / "vault"
    store = MemoryStore(vault)
    store.replace({"validated_memory": memories, "rejected_memory": []})
    return vault


def test_package_adapter_and_bare_module_preserve_identity() -> None:
    adapter = _load_adapter()
    canonical = importlib.import_module("brain_eleven.lifecycle.dedupe")
    bare = sys.modules["dedupe_validated_memory"]

    assert plan_dedupe is canonical.plan_dedupe
    assert adapter.plan_dedupe is canonical.plan_dedupe
    assert bare.plan_dedupe is canonical.plan_dedupe
    assert adapter.main is canonical.main
    assert adapter.SUPERSESSION_NOTE is canonical.SUPERSESSION_NOTE


def test_adapter_contains_no_dedupe_implementation() -> None:
    tree = ast.parse(ADAPTER_PATH.read_text(encoding="utf-8"))
    definitions = [
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
    ]
    assert definitions == ["_load_canonical"]
    source = ADAPTER_PATH.read_text(encoding="utf-8")
    assert "MemoryLifecycleManager(" not in source
    assert "defaultdict" not in source


def test_equal_timestamp_winner_is_deterministic_and_superseded_is_ignored() -> None:
    records = [
        _memory("z-winner-by-order-would-be-wrong", "2026-09-12T10:00:00"),
        _memory("a-canonical-by-id", "2026-09-12T10:00:00"),
        _memory("already-superseded", "2026-09-12T09:00:00", status="superseded"),
    ]

    expected = [("z-winner-by-order-would-be-wrong", "a-canonical-by-id", "fp-shared", "duplicate z-winner-by-order-would-be-wrong")]
    assert plan_dedupe(records) == expected
    assert plan_dedupe(list(reversed(records))) == expected


def test_apply_is_idempotent_and_second_run_does_not_save(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    vault = _seed_vault(
        tmp_path,
        [_memory("canonical", "2026-09-12T10:00:00"), _memory("loser", "2026-09-12T11:00:00")],
    )
    canonical = importlib.import_module("brain_eleven.lifecycle.dedupe")
    original = canonical.MemoryLifecycleManager
    calls: list[str] = []

    class SpyManager:
        def __init__(self, vault_path: str):
            self.inner = original(vault_path)
            self.memories = self.inner.memories

        def supersede_memory(self, *args):
            return self.inner.supersede_memory(*args)

        def save(self):
            calls.append("save")
            return self.inner.save()

    monkeypatch.setattr(canonical, "MemoryLifecycleManager", SpyManager)
    assert canonical.main(["--apply", str(vault)]) == 0
    assert canonical.main(["--apply", str(vault)]) == 0
    assert calls == ["save"]

    document = MemoryStore(vault).load()
    assert len(document["validated_memory"]) == 2
    assert {record["memory_id"] for record in document["validated_memory"]} == {"canonical", "loser"}
    assert next(record for record in document["validated_memory"] if record["memory_id"] == "loser")["status"] == "superseded"


def test_save_rejects_stale_snapshot_without_silent_overwrite(tmp_path: Path) -> None:
    vault = _seed_vault(
        tmp_path,
        [_memory("canonical", "2026-09-12T10:00:00"), _memory("loser", "2026-09-12T11:00:00")],
    )
    manager = MemoryLifecycleManager(str(vault))
    MemoryStore(vault).append(_memory("concurrent", "2026-09-12T12:00:00"))
    manager.supersede_memory("loser", "canonical", "test stale snapshot")

    with pytest.raises(MemoryStoreConflict):
        manager.save()

    current_ids = {
        record["memory_id"] for record in MemoryStore(vault).load()["validated_memory"]
    }
    assert current_ids == {"canonical", "loser", "concurrent"}
    assert next(
        record for record in MemoryStore(vault).load()["validated_memory"]
        if record["memory_id"] == "loser"
    )["status"] == "active"


def test_dry_run_has_no_canonical_effect_and_apply_creates_backup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    vault = _seed_vault(
        tmp_path,
        [_memory("canonical", "2026-09-12T10:00:00"), _memory("loser", "2026-09-12T11:00:00")],
    )
    canonical = importlib.import_module("brain_eleven.lifecycle.dedupe")
    original = canonical.MemoryLifecycleManager
    calls: list[str] = []

    class SpyManager:
        def __init__(self, vault_path: str):
            self.inner = original(vault_path)
            self.memories = self.inner.memories

        def save(self):
            calls.append("save")
            return self.inner.save()

        def supersede_memory(self, *args):
            return self.inner.supersede_memory(*args)

    monkeypatch.setattr(canonical, "MemoryLifecycleManager", SpyManager)
    before = MemoryStore(vault).load()
    assert canonical.main([str(vault)]) == 0
    assert calls == []
    assert MemoryStore(vault).load() == before

    assert canonical.main(["--apply", str(vault)]) == 0
    assert calls == ["save"]
    assert MemoryStore(vault).backup_path.exists()


def test_dedupe_preserves_record_count_and_id_set(tmp_path: Path) -> None:
    vault = _seed_vault(
        tmp_path,
        [
            _memory("canonical", "2026-09-12T10:00:00"),
            _memory("loser", "2026-09-12T11:00:00"),
            {**_memory("resolved", "2026-09-12T12:00:00"), "status": "resolved"},
        ],
    )
    before = MemoryStore(vault).load()
    importlib.import_module("brain_eleven.lifecycle.dedupe").main(["--apply", str(vault)])
    after = MemoryStore(vault).load()

    assert len(after["validated_memory"]) == len(before["validated_memory"])
    assert {item["memory_id"] for item in after["validated_memory"]} == {
        item["memory_id"] for item in before["validated_memory"]
    }
