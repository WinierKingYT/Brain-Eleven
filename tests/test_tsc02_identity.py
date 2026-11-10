"""TSC-02 project identity and registry-lineage safety evidence."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from brain_eleven.projects.identity import (
    ROOT_IDENTITY_PATTERN,
    project_root_identity,
)
from project_registry import ProjectRegistry
from state_store import StateService
from task_state_context import TaskStateComposer, TaskStateLineage, TaskStateLineageError


SOURCE = {"type": "user", "reference": "tsc-02-test"}


def _configured(tmp_path: Path):
    project = tmp_path / "project-a"
    project.mkdir()
    ProjectRegistry(tmp_path).register(project, project_id="project-a")
    StateService(tmp_path).init_project("project-a", source=SOURCE)
    return project, TaskStateComposer(tmp_path, project).compose("Implement safe persistence.")


def test_root_identity_is_opaque_fixed_format_and_path_free(tmp_path):
    root = tmp_path / "private-project"
    identity = project_root_identity(root)

    assert ROOT_IDENTITY_PATTERN.fullmatch(identity)
    assert str(root) not in identity
    assert identity == project_root_identity(root.resolve())


def test_composer_emits_lineage_without_changing_task_state_fields(tmp_path):
    _project, context = _configured(tmp_path)
    payload = context.to_dict()

    assert list(payload) == ["schema_version", "task", "state", "lineage"]
    assert payload["schema_version"] == 1
    assert payload["lineage"]["project_id"] == "project-a"
    assert payload["lineage"]["registry_revision"] == 1
    assert payload["lineage"]["root_identity"].startswith("project-root-v1:")
    assert str(tmp_path) not in json.dumps(payload["lineage"])


def test_valid_relocation_preserves_project_id_but_changes_root_identity(tmp_path):
    project, old_context = _configured(tmp_path)
    moved = tmp_path / "moved-project"
    moved.mkdir()
    registry = ProjectRegistry(tmp_path)
    registry.relocate("project-a", moved)

    new_context = TaskStateComposer(tmp_path, moved).compose("Implement safe persistence.")

    assert new_context.lineage.project_id == old_context.lineage.project_id == "project-a"
    assert new_context.lineage.root_identity != old_context.lineage.root_identity
    assert project.exists()


def test_composer_rejects_registry_change_between_reads(tmp_path, monkeypatch):
    project, _context = _configured(tmp_path)
    composer = TaskStateComposer(tmp_path, project)
    original_resolve = composer.resolver.resolve

    def race(project_id):
        state = original_resolve(project_id)
        ProjectRegistry(tmp_path).rename(project_id, "renamed-during-compose")
        return state

    monkeypatch.setattr(composer.resolver, "resolve", race)

    with pytest.raises(TaskStateLineageError, match="registry changed"):
        composer.compose("Implement safe persistence.")


def test_unresolved_and_global_lineage_are_explicit_and_project_free(tmp_path):
    unknown = TaskStateComposer(tmp_path, tmp_path / "unknown").compose("Explain task state.")
    assert unknown.lineage == TaskStateLineage(status="unresolved")
    assert unknown.task.project.project_id is None
    assert unknown.state.project_id is None
