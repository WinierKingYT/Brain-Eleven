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
    resolve_retrieval_project,
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

    project_id = compiler_module.resolve_session_project_id(vault, project_root)
    assert project_id == registered["project_id"]
    assert path.read_bytes() == before
    compiler = compiler_module.ContextCompiler(str(vault), project_id=project_id)
    compiler._load_validated_memories()
    assert {memory["memory_id"] for memory in compiler._rank_memories(limit=10)} == {"g", "p"}


def test_archived_project_defaults_to_global_only_but_historical_scope_is_explicit(tmp_path):
    compiler_module = _load_script("phase13_archived_context_compiler", "context-compiler.py")
    vault = tmp_path / "vault"
    archived_root = tmp_path / "archived-project"
    archived_root.mkdir()
    (vault / ".claude").mkdir(parents=True)
    records = [
        _memory("g", "global fact"),
        _memory("a", "archived project fact", PROJECT_SCOPE, "proj-archived", "Archived"),
        _memory("b", "other project fact", PROJECT_SCOPE, "proj-other", "Other"),
    ]
    (vault / ".claude" / "validated-memory.json").write_text(
        json.dumps({"validated_memory": records}), encoding="utf-8"
    )
    registry = ProjectRegistry(vault)
    registry.register(archived_root, project_id="proj-archived")
    registry.set_status("proj-archived", "archived")

    assert compiler_module.resolve_session_project_id(vault, archived_root) is None
    default_compiler = compiler_module.ContextCompiler(str(vault), project_id=None)
    default_compiler._load_validated_memories()
    assert [memory["memory_id"] for memory in default_compiler._rank_memories(limit=10)] == ["g"]

    historical_id, _label = resolve_retrieval_project(
        archived_root,
        registry_path(vault),
        include_archived=True,
    )
    historical_compiler = compiler_module.ContextCompiler(
        str(vault), project_id=historical_id, retrieval_scope="project"
    )
    historical_compiler._load_validated_memories()
    assert [memory["memory_id"] for memory in historical_compiler._rank_memories(limit=10)] == ["a"]

    all_compiler = compiler_module.ContextCompiler(
        str(vault), project_id=historical_id, retrieval_scope="all"
    )
    all_compiler._load_validated_memories()
    assert {memory["memory_id"] for memory in all_compiler._rank_memories(limit=10)} == {"g", "a", "b"}


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
    assert installer._managed_settings_entries(home)[0][1] in commands
    assert (claude / "commands" / "remember.md").exists()

    removed = installer.uninstall(home)
    assert removed["status"] == "uninstalled"
    assert "keep-me" in [hook["command"] for _event, _group, hook in installer._iter_hook_commands(json.loads(settings_path.read_text(encoding="utf-8")))]
    assert not (claude / "commands" / "remember.md").exists()


def test_installer_recovers_a_matching_partial_legacy_install(tmp_path):
    installer = _load_script("phase14_partial_installer", "install-cross-project-memory.py")
    home = tmp_path / "home"
    claude = home / ".claude"
    hooks = claude / "hooks"
    commands = claude / "commands"
    hooks.mkdir(parents=True)
    commands.mkdir()
    vault = tmp_path / "vault"

    (commands / "remember.md").write_text(
        installer._render(installer.TEMPLATE_ROOT / "commands" / "remember.md", vault),
        encoding="utf-8",
    )
    (hooks / "brain-eleven-remember-opt-in").write_text(
        installer._render(installer.TEMPLATE_ROOT / "hooks" / "brain-eleven-remember-opt-in", vault),
        encoding="utf-8",
    )
    (claude / "settings.json").write_text(
        json.dumps({"hooks": {"SessionEnd": [{"hooks": [{"type": "command", "command": "bash ~/.claude/hooks/brain-eleven-remember-opt-in"}]}]}}),
        encoding="utf-8",
    )

    result = installer.install(home, vault)

    assert result["status"] == "installed"
    assert (hooks / "brain-eleven-session-start").exists()
    assert (claude / installer.MANIFEST_NAME).exists()
    settings = json.loads((claude / "settings.json").read_text(encoding="utf-8"))
    commands = [hook["command"] for _event, _group, hook in installer._iter_hook_commands(settings)]
    assert installer._managed_settings_entries(home)[0][1] in commands


def test_installer_conflict_leaves_partial_global_state_untouched(tmp_path):
    installer = _load_script("phase14_conflict_installer", "install-cross-project-memory.py")
    home = tmp_path / "home"
    claude = home / ".claude"
    commands = claude / "commands"
    commands.mkdir(parents=True)
    settings_path = claude / "settings.json"
    original_settings = json.dumps({"hooks": {"SessionStart": [{"hooks": [{"type": "command", "command": "keep-me"}]}]}})
    settings_path.write_text(original_settings, encoding="utf-8")
    (commands / "remember.md").write_text("user-owned custom command", encoding="utf-8")

    result = installer.install(home, tmp_path / "vault")

    assert result["status"] == "conflict"
    assert settings_path.read_text(encoding="utf-8") == original_settings
    assert not (claude / "hooks" / "brain-eleven-session-start").exists()
    assert not (claude / installer.MANIFEST_NAME).exists()


def test_installer_upgrades_known_legacy_artifacts_with_backups(tmp_path):
    installer = _load_script("phase14_upgrade_installer", "install-cross-project-memory.py")
    home = tmp_path / "home"
    claude = home / ".claude"
    commands = claude / "commands"
    hooks = claude / "hooks"
    commands.mkdir(parents=True)
    hooks.mkdir()
    vault = tmp_path / "vault"
    legacy_remember = installer._render(installer.LEGACY_TEMPLATE_ROOT / "remember-v1.md", vault)
    legacy_hook = installer._render(
        installer.LEGACY_TEMPLATE_ROOT / "brain-eleven-remember-opt-in-v1", vault
    )
    remember_path = commands / "remember.md"
    hook_path = hooks / "brain-eleven-remember-opt-in"
    remember_path.write_text(legacy_remember, encoding="utf-8")
    hook_path.write_text(legacy_hook, encoding="utf-8")

    result = installer.install(home, vault)

    upgraded = {Path(item["path"]).name: item for item in result["files"] if item["status"] == "upgrade"}
    assert set(upgraded) == {"remember.md", "brain-eleven-remember-opt-in"}
    assert Path(upgraded["remember.md"]["backup"]).read_text(encoding="utf-8") == legacy_remember
    assert Path(upgraded["brain-eleven-remember-opt-in"]["backup"]).read_text(encoding="utf-8") == legacy_hook
    assert remember_path.read_text(encoding="utf-8") == installer._render(
        installer.TEMPLATE_ROOT / "commands" / "remember.md", vault
    )
    assert hook_path.read_text(encoding="utf-8") == installer._render(
        installer.TEMPLATE_ROOT / "hooks" / "brain-eleven-remember-opt-in", vault
    )


def test_installer_upgrades_a_manifest_owned_artifact(tmp_path):
    installer = _load_script("phase14_manifest_upgrade_installer", "install-cross-project-memory.py")
    home = tmp_path / "home"
    vault = tmp_path / "vault"
    command_path = home / ".claude" / "commands" / "remember.md"
    command_path.parent.mkdir(parents=True)
    prior_content = "known managed command version one\n"
    command_path.write_text(prior_content, encoding="utf-8")
    manifest_path = home / ".claude" / installer.MANIFEST_NAME
    manifest_path.write_text(
        json.dumps(
            {
                "version": 1,
                "vault": str(vault),
                "files": {str(command_path): installer._sha256_text(prior_content)},
                "settings_commands": [],
            }
        ),
        encoding="utf-8",
    )

    result = installer.install(home, vault)

    upgraded = next(item for item in result["files"] if item["path"] == str(command_path))
    assert upgraded["status"] == "upgrade"
    assert Path(upgraded["backup"]).read_text(encoding="utf-8") == prior_content


def test_global_hook_templates_resolve_python_portably():
    template_root = SCRIPTS.parent / "templates" / "claude" / "hooks"
    for name in ("brain-eleven-session-start", "brain-eleven-remember-opt-in"):
        template = (template_root / name).read_text(encoding="utf-8")
        assert 'PYTHON_BIN="${PYTHON:-python3}"' in template
        assert 'command -v "$PYTHON_BIN"' in template
        assert 'command -v wslpath' in template
        assert 'BASH_REMATCH[1],,' in template


def test_windows_installer_uses_a_direct_wsl_hook_path(tmp_path):
    installer = _load_script("phase14_wsl_path_installer", "install-cross-project-memory.py")
    command = installer._shell_hook_command(tmp_path / "home", "brain-eleven-session-start")

    if installer.os.name == "nt":
        assert command.startswith("bash /mnt/")
    else:
        assert command.startswith("bash /")
    assert "brain-eleven-session-start" in command


def test_installer_replaces_only_legacy_managed_hook_commands(tmp_path):
    installer = _load_script("phase14_hook_command_installer", "install-cross-project-memory.py")
    home = tmp_path / "home"
    claude = home / ".claude"
    claude.mkdir(parents=True)
    settings_path = claude / "settings.json"
    legacy_start, legacy_end = sorted(installer._legacy_settings_commands())
    settings_path.write_text(
        json.dumps(
            {
                "hooks": {
                    "SessionStart": [{"hooks": [{"type": "command", "command": legacy_start}]}],
                    "SessionEnd": [{"hooks": [{"type": "command", "command": legacy_end}]}],
                    "UserPromptSubmit": [{"hooks": [{"type": "command", "command": "keep-me"}]}],
                }
            }
        ),
        encoding="utf-8",
    )

    installer.install(home, tmp_path / "vault")

    settings = json.loads(settings_path.read_text(encoding="utf-8"))
    commands = [hook["command"] for _event, _group, hook in installer._iter_hook_commands(settings)]
    assert legacy_start not in commands
    assert legacy_end not in commands
    assert "keep-me" in commands
    assert {command for _event, command in installer._managed_settings_entries(home)} <= set(commands)
