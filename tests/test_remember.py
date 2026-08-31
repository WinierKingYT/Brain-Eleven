#!/usr/bin/env python3
"""Tests for the cross-project memory capture adapter and opt-in gate."""

import json
import importlib.util
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from knowledge_graph import KnowledgeGraph  # noqa: E402
from project_registry import ProjectRegistry, ProjectRegistryError  # noqa: E402
from remember import (  # noqa: E402
    default_project_id,
    is_project_opted_in,
    remember,
)
from remember_opt_in import main as opt_in_main  # noqa: E402


def _load_script(name, filename):
    script = Path(__file__).parent.parent / "scripts" / filename
    spec = importlib.util.spec_from_file_location(name, script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def vault(tmp_path):
    vault_path = tmp_path / "brain-eleven"
    (vault_path / ".claude").mkdir(parents=True)
    return vault_path


def test_remember_persists_project_and_rebuilds_graph(vault):
    result = remember(
        type_="decision",
        content="Decided to use Redis for the imported project",
        confidence=1.0,
        project="promtgen",
        vault_path=vault,
    )

    assert result["status"] == "created"
    assert result["project"] == "promtgen"
    assert result["is_new"] is True

    stored = json.loads((vault / ".claude" / "validated-memory.json").read_text(encoding="utf-8"))
    assert stored["validated_memory"][0]["project"] == "promtgen"

    graph = KnowledgeGraph(str(vault))
    assert graph.get_entity(result["memory_id"]) is not None


def test_remember_dedup_isolated_by_project_namespace(vault):
    first = remember(
        type_="lesson",
        content="The imported project uses deterministic tests",
        confidence=1.0,
        project="project-a",
        vault_path=vault,
    )
    same_project = remember(
        type_="lesson",
        content="The imported project uses deterministic tests",
        confidence=1.0,
        project="project-a",
        vault_path=vault,
    )
    other_project = remember(
        type_="lesson",
        content="The imported project uses deterministic tests",
        confidence=1.0,
        project="project-b",
        vault_path=vault,
    )

    assert same_project["status"] == "duplicate_returned_existing"
    assert same_project["memory_id"] == first["memory_id"]
    assert same_project["project"] == "project-a"
    assert other_project["status"] == "created"
    assert other_project["memory_id"] != first["memory_id"]
    assert other_project["project"] == "project-b"


def test_default_project_id_does_not_persist_absolute_path(tmp_path):
    project_root = tmp_path / "private-client-project"
    project_root.mkdir()

    assert default_project_id(project_root) == "private-client-project"


def test_remember_uses_registry_identity_after_project_relocation(vault, tmp_path):
    old_root = tmp_path / "old-project"
    new_root = tmp_path / "moved-project"
    old_root.mkdir()
    new_root.mkdir()

    first = remember(
        type_="decision",
        content="The project uses a local cache",
        confidence=1.0,
        vault_path=vault,
        project_root=old_root,
    )
    registry = ProjectRegistry(vault)
    registry.relocate(first["project_id"], new_root)

    second = remember(
        type_="lesson",
        content="The project tests run offline",
        confidence=1.0,
        vault_path=vault,
        project_root=new_root,
    )

    assert second["project_id"] == first["project_id"]


def test_registry_is_the_only_proactive_capture_authority(vault, tmp_path):
    config = vault / ".claude" / "remember-config.json"
    project = tmp_path / "AllowedProject"
    other = tmp_path / "OtherProject"
    project.mkdir()
    other.mkdir()
    config.write_text(
        json.dumps({"proactive_opt_in_projects": [str(project)]}),
        encoding="utf-8",
    )

    registry = ProjectRegistry(vault)
    registry.register(project, project_id="proj-allowed")

    assert is_project_opted_in(project, vault) is False
    registry.set_proactive_capture("proj-allowed", True)
    assert is_project_opted_in(project, vault) is True
    assert is_project_opted_in(other, vault) is False


def test_legacy_config_requires_explicit_registry_migration(vault, tmp_path):
    config = vault / ".claude" / "remember-config.json"
    project = tmp_path / "legacy-project"
    project.mkdir()
    config.write_text(
        json.dumps({"proactive_opt_in_projects": [str(project)]}),
        encoding="utf-8",
    )

    registry = ProjectRegistry(vault)
    assert is_project_opted_in(project, vault) is False

    migrated = registry.migrate_legacy_opt_in_config(config)
    assert len(migrated["migrated"]) == 1
    assert is_project_opted_in(project, vault) is True

    rerun = registry.migrate_legacy_opt_in_config(config)
    assert rerun["migrated"] == []
    assert rerun["unchanged"] == migrated["migrated"]


def test_legacy_migration_cli_enables_canonical_registry_policy(vault, tmp_path, capsys):
    config = vault / ".claude" / "remember-config.json"
    project = tmp_path / "cli-legacy-project"
    project.mkdir()
    config.write_text(
        json.dumps({"proactive_opt_in_projects": [str(project)]}),
        encoding="utf-8",
    )

    registry_cli = _load_script("project_registry_cli", "project-registry.py")
    assert registry_cli.main(
        ["--vault", str(vault), "migrate-legacy-opt-in", "--config", str(config)]
    ) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "migrated"
    assert is_project_opted_in(project, vault) is True


def test_missing_or_malformed_legacy_config_cannot_enable_capture(vault, tmp_path):
    missing = tmp_path / "missing.json"
    malformed = tmp_path / "malformed.json"
    malformed.write_text("{not-json", encoding="utf-8")
    registry = ProjectRegistry(vault)

    assert registry.migrate_legacy_opt_in_config(missing)["status"] == "missing"
    with pytest.raises(ProjectRegistryError):
        registry.migrate_legacy_opt_in_config(malformed)
    assert is_project_opted_in(tmp_path, vault) is False


def test_archived_project_cannot_proactively_capture(vault, tmp_path):
    project = tmp_path / "archived-project"
    project.mkdir()
    registry = ProjectRegistry(vault)
    registry.register(project, project_id="proj-archived", proactive_capture=True)

    assert is_project_opted_in(project, vault) is True
    archived = registry.set_status("proj-archived", "archived")
    assert archived["proactive_capture"] is False
    assert is_project_opted_in(project, vault) is False
    with pytest.raises(ProjectRegistryError):
        registry.set_proactive_capture("proj-archived", True)


def test_opt_in_cli_uses_canonical_registry_policy(vault, tmp_path, capsys):
    allowed = tmp_path / "allowed"
    denied = tmp_path / "denied"
    allowed.mkdir()
    denied.mkdir()

    registry = ProjectRegistry(vault)
    registry.register(allowed, project_id="proj-allowed", proactive_capture=True)

    assert opt_in_main(["--project-root", str(allowed), "--vault", str(vault)]) == 0
    allowed_result = json.loads(capsys.readouterr().out)
    assert allowed_result == {
        "opted_in": True,
        "allowed": True,
        "reason": "enabled",
        "project_id": "proj-allowed",
    }
    assert opt_in_main(["--project-root", str(denied), "--vault", str(vault)]) == 1
    assert json.loads(capsys.readouterr().out)["reason"] == "unregistered"


def test_global_hook_uses_registry_policy_not_legacy_config():
    hook = (
        Path(__file__).parent.parent
        / "templates"
        / "claude"
        / "hooks"
        / "brain-eleven-remember-opt-in"
    ).read_text(encoding="utf-8")

    assert '--vault "$BRAIN_ELEVEN_VAULT"' in hook
    assert "remember-config.json" not in hook
