#!/usr/bin/env python3
"""Tests for the cross-project memory capture adapter and opt-in gate."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from knowledge_graph import KnowledgeGraph  # noqa: E402
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


def test_remember_dedup_keeps_canonical_identity_and_origin(vault):
    first = remember(
        type_="lesson",
        content="The imported project uses deterministic tests",
        confidence=1.0,
        project="project-a",
        vault_path=vault,
    )
    second = remember(
        type_="lesson",
        content="The imported project uses deterministic tests",
        confidence=1.0,
        project="project-b",
        vault_path=vault,
    )

    assert second["status"] == "duplicate_returned_existing"
    assert second["memory_id"] == first["memory_id"]
    assert second["project"] == "project-a"


def test_default_project_id_does_not_persist_absolute_path(tmp_path):
    project_root = tmp_path / "private-client-project"
    project_root.mkdir()

    assert default_project_id(project_root) == "private-client-project"


def test_opt_in_requires_exact_normalized_absolute_root(tmp_path):
    config = tmp_path / "remember-config.json"
    project = tmp_path / "AllowedProject"
    other = tmp_path / "OtherProject"
    project.mkdir()
    other.mkdir()
    config.write_text(
        json.dumps({"proactive_opt_in_projects": [str(project).replace("\\", "/").upper()]}),
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
