#!/usr/bin/env python3
"""Tests for the cross-project memory capture adapter and opt-in gate."""

import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from knowledge_graph import KnowledgeGraph  # noqa: E402
from project_registry import ProjectRegistry  # noqa: E402
from remember import (  # noqa: E402
    config_path,
    default_project_id,
    is_project_opted_in,
    remember,
)
from remember_opt_in import main as opt_in_main  # noqa: E402


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


def test_opt_in_requires_exact_normalized_absolute_root(tmp_path):
    config = tmp_path / "remember-config.json"
    project = tmp_path / "AllowedProject"
    other = tmp_path / "OtherProject"
    project.mkdir()
    other.mkdir()
    configured_root = str(project).replace("\\", "/")
    if os.name == "nt":
        configured_root = configured_root.upper()
    config.write_text(
        json.dumps({"proactive_opt_in_projects": [configured_root]}),
        encoding="utf-8",
    )

    assert is_project_opted_in(project, config) is True
    assert is_project_opted_in(other, config) is False


def test_missing_or_malformed_opt_in_config_fails_closed(tmp_path):
    missing = tmp_path / "missing.json"
    malformed = tmp_path / "malformed.json"
    malformed.write_text("{not-json", encoding="utf-8")

    assert is_project_opted_in(tmp_path, missing) is False
    assert is_project_opted_in(tmp_path, malformed) is False


def test_opt_in_cli_returns_success_only_for_allowed_root(tmp_path, capsys):
    config = tmp_path / "remember-config.json"
    allowed = tmp_path / "allowed"
    denied = tmp_path / "denied"
    allowed.mkdir()
    denied.mkdir()
    config.write_text(
        json.dumps({"proactive_opt_in_projects": [str(allowed)]}),
        encoding="utf-8",
    )

    assert opt_in_main(["--project-root", str(allowed), "--config", str(config)]) == 0
    assert json.loads(capsys.readouterr().out)["opted_in"] is True
    assert opt_in_main(["--project-root", str(denied), "--config", str(config)]) == 1
    assert json.loads(capsys.readouterr().out)["opted_in"] is False


def test_config_path_points_inside_vault(vault):
    assert config_path(vault) == vault / ".claude" / "remember-config.json"
