#!/usr/bin/env python3
"""Phase 14 regression tests for scope, migration, graph provenance and install."""

import importlib.util
import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

from entity_extractor import EntityExtractor  # noqa: E402
from knowledge_graph import KnowledgeGraph  # noqa: E402
from memory_scope import (  # noqa: E402
    GLOBAL_SCOPE,
    PROJECT_SCOPE,
    filter_memories,
    legacy_project_id,
    project_identity,
    resolved_project_identity,
    scoped_fingerprint,
)
from project_registry import ProjectRegistry, ProjectRegistryError, registry_path  # noqa: E402


def _load_script(name, filename):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _memory(memory_id, content, scope="global", project_id="", project=""):
    return {
        "memory_id": memory_id,
        "type": "decision",
        "content": content,
        "scope": scope,
        "project": project,
        "project_id": project_id,
        "status": "active",
        "confidence": 0.9,
        "quality_score": 0.9,
        "timestamp": "2026-08-31T12:00:00",
        "is_approved": True,
    }


def test_project_fingerprint_isolated_from_global_and_other_projects():
    content = "Use Redis for caching"
    assert scoped_fingerprint(content, GLOBAL_SCOPE) != scoped_fingerprint(
        content, PROJECT_SCOPE, "project-a"
    )
    assert scoped_fingerprint(content, PROJECT_SCOPE, "project-a") != scoped_fingerprint(
        content, PROJECT_SCOPE, "project-b"
    )


def test_project_fingerprint_includes_memory_type():
    content = "Use Redis for caching"
    assert scoped_fingerprint(content, GLOBAL_SCOPE, type_="decision") != scoped_fingerprint(
        content, GLOBAL_SCOPE, type_="lesson"
    )


def test_project_registry_preserves_identity_when_root_moves(tmp_path):
    vault = tmp_path / "vault"
    registry = ProjectRegistry(vault)
    original_root = tmp_path / "old-name"
    moved_root = tmp_path / "new-name"
    original_root.mkdir()
    moved_root.mkdir()

    first = registry.register(original_root, project_label="Old Name")
    relocated = registry.relocate(first["project_id"], moved_root)
    renamed = registry.rename(first["project_id"], "New Name")

    assert relocated["project_id"] == first["project_id"]
    assert registry.resolve(moved_root)["project_id"] == first["project_id"]
    assert renamed["project_label"] == "New Name"
    assert registry.resolve(original_root) is None


def test_project_registry_rejects_duplicate_root_identity(tmp_path):
    registry = ProjectRegistry(tmp_path / "vault")
    root = tmp_path / "project"
    root.mkdir()
    registry.register(root, project_id="proj-a")

    with pytest.raises(ProjectRegistryError):
        registry.register(root, project_id="proj-b")


def test_retrieval_identity_resolution_never_registers_unknown_project(tmp_path):
    vault = tmp_path / "vault"
    unknown_root = tmp_path / "unknown-project"
    unknown_root.mkdir()
    path = registry_path(vault)

    assert resolved_project_identity(unknown_root, path) is None
    assert not path.exists()

    registry = ProjectRegistry(vault)
    registered = registry.register(unknown_root, project_id="proj-known")
    before = path.read_bytes()

    assert resolved_project_identity(unknown_root, path) == (
        registered["project_id"], registered["project_label"]
    )
    assert path.read_bytes() == before


def test_default_retrieval_is_global_only_without_project():
    memories = [
        _memory("g", "global fact"),
        _memory("a", "project A fact", PROJECT_SCOPE, "a", "A"),
    ]
    assert [m["memory_id"] for m in filter_memories(memories)] == ["g"]
    assert [m["memory_id"] for m in filter_memories(memories, "a")] == ["g", "a"]
    assert [m["memory_id"] for m in filter_memories(memories, "b")] == ["g"]
    assert [m["memory_id"] for m in filter_memories(memories, retrieval_scope="all")] == ["g", "a"]


def test_context_compiler_retrieves_global_and_current_project_only(tmp_path):
    compiler_module = _load_script("phase14_context_compiler", "context-compiler.py")
    vault = tmp_path / "vault"
    (vault / ".claude").mkdir(parents=True)
    records = [
        _memory("g", "global fact"),
        _memory("a", "project A fact", PROJECT_SCOPE, "a", "A"),
        _memory("b", "project B fact", PROJECT_SCOPE, "b", "B"),
    ]
    for record in records:
        record["timestamp"] = "2026-08-31T12:00:00"
    (vault / ".claude" / "validated-memory.json").write_text(
        json.dumps({"validated_memory": records}), encoding="utf-8"
    )

    compiler = compiler_module.ContextCompiler(str(vault), project_id="a")
    compiler._load_validated_memories()
    ranked_ids = {m["memory_id"] for m in compiler._rank_memories(limit=10)}

    assert ranked_ids == {"g", "a"}


def test_session_project_resolution_is_read_only_and_unknown_is_global_only(tmp_path):
    compiler_module = _load_script("phase14_context_compiler_read_only", "context-compiler.py")
    vault = tmp_path / "vault"
    project_root = tmp_path / "unregistered-project"
    project_root.mkdir()
    path = registry_path(vault)
    (vault / ".claude").mkdir(parents=True)
    (vault / ".claude" / "validated-memory.json").write_text(
        json.dumps(
            {
                "validated_memory": [
                    _memory("g", "global fact"),
                    _memory("p", "project fact", PROJECT_SCOPE, "proj-session", "Session"),
                ]
            }
        ),
        encoding="utf-8",
    )

    assert compiler_module.resolve_session_project_id(vault, project_root) is None
    assert not path.exists()
    compiler = compiler_module.ContextCompiler(str(vault), project_id=None)
    compiler._load_validated_memories()
    assert [memory["memory_id"] for memory in compiler._rank_memories(limit=10)] == ["g"]

    registered = ProjectRegistry(vault).register(project_root, project_id="proj-session")
    before = path.read_bytes()

    assert compiler_module.resolve_session_project_id(vault, project_root) == registered["project_id"]
    assert path.read_bytes() == before


def test_legacy_project_label_gets_stable_compatibility_id():
    assert legacy_project_id("PromtGen") == legacy_project_id("promtgen")


def test_conflict_detection_does_not_cross_project_boundaries(tmp_path):
    validator_module = _load_script("phase14_memory_validator", "memory-validator.py")
    vault = tmp_path / "vault"
    (vault / ".claude").mkdir(parents=True)
    project_a = project_identity(tmp_path / "project-a")[0]
    project_b = project_identity(tmp_path / "project-b")[0]
    (vault / ".claude" / "validated-memory.json").write_text(
        json.dumps({"validated_memory": [_memory("prior", "Use Redis", PROJECT_SCOPE, project_a, "A")]}),
        encoding="utf-8",
    )

    validator = validator_module.MemoryValidator(str(vault))
    candidate, issues, is_new = validator.validate_single(
        "decision", "Don't use Redis", project="B", project_id=project_b, confidence=1.0
    )

    assert is_new is True
    assert candidate.project_id == project_b
    assert not any(issue.type == "contradiction" for issue in issues)


def test_migration_is_idempotent_and_preserves_identity(tmp_path):
    migration = _load_script("phase14_migration", "migrate-memory-scope.py")
    vault = tmp_path / "vault"
    (vault / ".claude").mkdir(parents=True)
    original = _memory("stable-id", "legacy project memory", project="LegacyProject")
    original.pop("scope")
    original.pop("project_id")
    original.pop("is_approved")
    (vault / ".claude" / "validated-memory.json").write_text(
        json.dumps({"validated_memory": [original], "rejected_memory": []}),
        encoding="utf-8",
    )

    first = migration.migrate(vault)
    data = json.loads((vault / ".claude" / "validated-memory.json").read_text(encoding="utf-8"))
    migrated = data["validated_memory"][0]
    assert first["status"] == "migrated"
    assert migrated["memory_id"] == "stable-id"
    assert migrated["scope"] == PROJECT_SCOPE
    assert migrated["project_id"] == legacy_project_id("LegacyProject")
    assert migrated["project_label"] == "LegacyProject"
    assert migrated["dedup_fingerprint"] == scoped_fingerprint(
        "legacy project memory", PROJECT_SCOPE, migrated["project_id"], "decision"
    )

    second = migration.migrate(vault)
    assert second["status"] == "unchanged"


def test_graph_exposes_project_provenance_and_filters_it(tmp_path):
    vault = tmp_path / "vault"
    (vault / ".claude").mkdir(parents=True)
    graph = KnowledgeGraph(str(vault))
    extractor = EntityExtractor(str(vault))
    project_id = "project-a"
    extractor.extract_from_memory(
        _memory("m-a", "Chose Redis for caching", PROJECT_SCOPE, project_id, "Project A"),
        graph,
    )
    extractor.extract_from_memory(_memory("m-g", "Global Redis guidance"), graph)

    assert graph.get_entity("project_project-a")["type"] == "PROJECT"
    assert graph.get_relationships(
        "m-a", rel_type="BELONGS_TO", retrieval_scope="all"
    )[0]["target"] == "project_project-a"
    assert {e["id"] for e in graph.find_entities(entity_type="DECISION", project_id=project_id)} == {"m-a", "m-g"}
    assert {e["id"] for e in graph.find_entities(entity_type="DECISION", project_id="other")} == {"m-g"}


def test_installer_preserves_unrelated_settings_and_is_reversible(tmp_path):
    installer = _load_script("phase14_installer", "install-cross-project-memory.py")
    home = tmp_path / "home"
    claude = home / ".claude"
    claude.mkdir(parents=True)
    settings_path = claude / "settings.json"
    settings_path.write_text(
        json.dumps({"hooks": {"SessionStart": [{"matcher": "startup", "hooks": [{"type": "command", "command": "keep-me"}]}]}}),
        encoding="utf-8",
    )

    result = installer.install(home, tmp_path / "vault")
    assert result["status"] == "installed"
    settings = json.loads(settings_path.read_text(encoding="utf-8"))
    commands = [hook["command"] for _event, _group, hook in installer._iter_hook_commands(settings)]
    assert "keep-me" in commands
    assert "bash ~/.claude/hooks/brain-eleven-session-start" in commands
    assert (claude / "commands" / "remember.md").exists()

    removed = installer.uninstall(home)
    assert removed["status"] == "uninstalled"
    assert "keep-me" in [hook["command"] for _event, _group, hook in installer._iter_hook_commands(json.loads(settings_path.read_text(encoding="utf-8")))]
    assert not (claude / "commands" / "remember.md").exists()
