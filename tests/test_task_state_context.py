"""Phase 16 composition contract tests."""

from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from project_registry import ProjectRegistry  # noqa: E402
from state_store import StateService  # noqa: E402
from task_state_context import TaskStateComposer  # noqa: E402


SOURCE = {"type": "user", "reference": "test"}
NOW = "2026-09-03T12:00:00Z"


def test_task_state_context_composes_runtime_task_with_inherited_state_constraints(tmp_path):
    project = tmp_path / "brain-eleven"
    ProjectRegistry(tmp_path).register(project, project_id="brain-eleven")
    service = StateService(tmp_path)
    service.init_project("brain-eleven", source=SOURCE, now=NOW)
    service.add_constraint(
        "brain-eleven",
        text="memory_foundation_frozen",
        expected_revision=1,
        source=SOURCE,
        record_id="con_01J00000000000000000000000",
        now=NOW,
    )

    context = TaskStateComposer(tmp_path, project).compose("Phase 17 ContextRouter planını tasarla.")

    assert context.task.project.project_id == "brain-eleven"
    assert context.state.status == "AVAILABLE"
    assert context.task.inherited_constraints == ("memory_foundation_frozen",)
    assert context.to_dict()["schema_version"] == 1


def test_unresolved_task_is_composed_with_explicit_unknown_state(tmp_path):
    context = TaskStateComposer(tmp_path, tmp_path / "unknown").compose("Explain the task state model.")

    assert context.task.project.status == "unresolved"
    assert context.state.status == "PROJECT_UNKNOWN"
