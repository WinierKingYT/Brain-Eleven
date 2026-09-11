"""Package-boundary and safety evidence for IG-07 D1 capture migration."""

from __future__ import annotations

import ast
import importlib
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from brain_eleven.memory.store import MemoryStore


def _capture_module():
    return importlib.import_module("brain_eleven.memory.capture")


def test_package_adapter_and_bare_import_share_capture_objects():
    canonical = _capture_module()
    adapter = importlib.import_module("scripts.remember")
    bare = importlib.import_module("remember")

    assert adapter.remember is canonical.remember
    assert bare.remember is canonical.remember
    assert adapter.evaluate_capture is canonical.evaluate_capture
    assert bare.evaluate_capture is canonical.evaluate_capture
    assert adapter.MemoryValidator is canonical.MemoryValidator
    assert bare.MemoryValidator is canonical.MemoryValidator


def test_capture_safety_uses_the_single_legacy_policy_object():
    canonical = _capture_module()
    legacy = importlib.import_module("capture_safety")

    assert canonical.evaluate_capture is legacy.evaluate_capture
    assert canonical.require_safe_capture is legacy.require_safe_capture


def test_remember_adapter_has_no_second_implementation():
    source_path = Path(__file__).parents[1] / "scripts" / "remember.py"
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    definitions = {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
    }

    assert definitions == {"_load_canonical"}
    source = source_path.read_text(encoding="utf-8")
    assert "validate_single_and_append" not in source
    assert "from brain_eleven.memory.store" not in source
    assert "MemoryStore(" not in source
    assert "json.dump" not in source
    assert "open(" not in source


def test_capture_does_not_copy_canonical_transaction_authority():
    source_path = Path(__file__).parents[1] / "brain_eleven" / "memory" / "capture.py"
    source = source_path.read_text(encoding="utf-8")

    assert "from brain_eleven.memory.store" not in source
    assert "MemoryStore(" not in source
    assert ".transact(" not in source
    assert "validate_single_and_append" in source


def test_duplicate_capture_does_not_change_revision_or_rebuild_graph(tmp_path, monkeypatch):
    capture = _capture_module()
    vault = tmp_path / "vault"
    (vault / ".claude").mkdir(parents=True)
    calls = []

    class FakeExtractor:
        def __init__(self, _vault):
            pass

        def build_graph(self):
            calls.append("build")
            return self

        def stats(self):
            return {"fake": True}

    monkeypatch.setattr(capture, "EntityExtractor", FakeExtractor)
    first = capture.remember(
        type_="decision",
        content="The package capture path is canonical",
        confidence=1.0,
        project="project-a",
        vault_path=vault,
    )
    revision = MemoryStore(vault).revision()
    second = capture.remember(
        type_="decision",
        content="The package capture path is canonical",
        confidence=1.0,
        project="project-a",
        vault_path=vault,
    )

    assert first["status"] == "created"
    assert second["status"] == "duplicate_returned_existing"
    assert second["memory_id"] == first["memory_id"]
    assert MemoryStore(vault).revision() == revision
    assert calls == ["build"]


def test_concurrent_replay_has_one_canonical_record(tmp_path, monkeypatch):
    capture = _capture_module()
    vault = tmp_path / "vault"
    (vault / ".claude").mkdir(parents=True)

    class FakeExtractor:
        def __init__(self, _vault):
            pass

        def build_graph(self):
            return self

        def stats(self):
            return {}

    monkeypatch.setattr(capture, "EntityExtractor", FakeExtractor)

    def write_once(_index):
        return capture.remember(
            type_="lesson",
            content="Concurrent replay remains idempotent",
            confidence=1.0,
            project="project-a",
            vault_path=vault,
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(write_once, range(2)))

    assert sorted(result["status"] for result in results) == [
        "created",
        "duplicate_returned_existing",
    ]
    assert len({result["memory_id"] for result in results}) == 1
    stored = json.loads(
        (vault / ".claude" / "validated-memory.json").read_text(encoding="utf-8")
    )
    assert len(stored["validated_memory"]) == 1


def test_projects_are_isolated_and_absolute_roots_are_not_persisted(tmp_path, monkeypatch):
    capture = _capture_module()
    vault = tmp_path / "vault"
    (vault / ".claude").mkdir(parents=True)
    project_a = tmp_path / "private-a"
    project_b = tmp_path / "private-b"
    project_a.mkdir()
    project_b.mkdir()

    class FakeExtractor:
        def __init__(self, _vault):
            pass

        def build_graph(self):
            return self

        def stats(self):
            return {}

    monkeypatch.setattr(capture, "EntityExtractor", FakeExtractor)
    first = capture.remember(
        type_="lesson",
        content="The same fact is scoped independently",
        confidence=1.0,
        vault_path=vault,
        project_root=project_a,
    )
    second = capture.remember(
        type_="lesson",
        content="The same fact is scoped independently",
        confidence=1.0,
        vault_path=vault,
        project_root=project_b,
    )

    assert first["status"] == second["status"] == "created"
    assert first["project_id"] != second["project_id"]
    stored_text = (vault / ".claude" / "validated-memory.json").read_text(encoding="utf-8")
    assert str(project_a) not in stored_text
    assert str(project_b) not in stored_text


def test_unsafe_capture_rejects_before_registry_access(tmp_path, monkeypatch):
    capture = _capture_module()
    vault = tmp_path / "vault"
    (vault / ".claude").mkdir(parents=True)

    class ExplodingRegistry:
        def __init__(self, _vault):
            raise AssertionError("registry must not be touched before safety")

    monkeypatch.setattr(capture, "ProjectRegistry", ExplodingRegistry)
    result = capture.remember(
        type_="decision",
        content="Authorization: Bearer abcdefghijklmnopqrstuvwxyz012345",
        vault_path=vault,
        project_root=tmp_path / "project",
    )

    assert result["accepted"] is False
    assert not (vault / ".claude" / "validated-memory.json").exists()


def test_opt_in_caller_uses_package_surface():
    caller = importlib.import_module("scripts.remember_opt_in")
    canonical = _capture_module()

    assert caller.proactive_capture_policy is canonical.proactive_capture_policy
    assert "remember" in sys.modules
