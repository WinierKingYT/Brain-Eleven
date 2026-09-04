"""Phase 16 task-envelope contract tests."""

from __future__ import annotations

import copy
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from task_model import (  # noqa: E402
    TASK_SCHEMA_VERSION,
    TaskAnalyzer,
    TaskProjectResolutionError,
    TaskValidationError,
    new_task_id,
    resolve_project,
    validate_task,
)
from project_registry import ProjectRegistry  # noqa: E402


def task_document():
    return {
        "schema_version": TASK_SCHEMA_VERSION,
        "task_id": "tsk_01J00000000000000000000000",
        "created_at": "2026-09-03T12:00:00Z",
        "lifecycle": "ANALYZED",
        "project": {
            "project_id": "brain-eleven",
            "status": "resolved",
            "source": "project_registry",
            "confidence": 1.0,
        },
        "request": {"raw": "Phase 17'nin planını hazırla."},
        "intent": {"value": "PLAN", "source": "task_analyzer", "confidence": 0.9},
        "operation": {"value": "design", "source": "task_analyzer", "confidence": 0.9},
        "requested_output": {"value": "implementation_plan", "source": "task_analyzer", "confidence": 0.9},
        "constraints": {"explicit": ["no_router"], "inherited": ["memory_foundation_frozen"]},
        "entities": ["phase-17", "context-router"],
        "domains": {"canonical": ["context-engine"], "discovered": ["task-model"]},
        "risk": {
            "level": {"value": "MEDIUM", "source": "task_analyzer", "confidence": 0.8},
            "flags": ["architecture_change"],
        },
        "context_needs": ["current_project_state", "relevant_decisions"],
        "ambiguities": [],
        "confidence": {"overall": 0.9, "project": 1.0, "intent": 0.9, "domains": 0.7},
    }


def test_valid_task_round_trips_without_losing_raw_request():
    source = task_document()
    source["request"]["raw"] = "  Türkçe   raw request korunur.  "

    task = validate_task(source)

    assert task.to_dict()["request"]["raw"] == "  Türkçe   raw request korunur.  "
    assert task.project.project_id == "brain-eleven"
    assert task.intent.value == "PLAN"


def test_unresolved_project_is_explicit_and_carries_no_identity():
    source = task_document()
    source["project"] = {
        "project_id": None,
        "status": "unresolved",
        "source": "project_registry",
        "confidence": 0.0,
    }

    task = validate_task(source)

    assert task.project.status == "unresolved"
    assert task.project.project_id is None


def test_rejects_resolved_project_without_identity():
    source = task_document()
    source["project"]["project_id"] = None

    with pytest.raises(TaskValidationError, match="requires project_id"):
        validate_task(source)


def test_rejects_unknown_fields_and_invalid_provenance():
    source = task_document()
    source["intent"]["source"] = "llm"

    with pytest.raises(TaskValidationError, match="source is unsupported"):
        validate_task(source)

    source = task_document()
    source["unexpected"] = True
    with pytest.raises(TaskValidationError, match="unknown field"):
        validate_task(source)


def test_explicit_constraints_and_task_links_require_stable_namespaces():
    source = task_document()
    source["parent_task_id"] = "tsk_01J00000000000000000000001"
    source["continuation_of"] = "tsk_01J00000000000000000000002"

    task = validate_task(source)

    assert task.explicit_constraints == ("no_router",)
    assert task.parent_task_id.startswith("tsk_")

    invalid = copy.deepcopy(source)
    invalid["continuation_of"] = "mem_123"
    with pytest.raises(TaskValidationError, match="tsk_ namespace"):
        validate_task(invalid)


def test_generated_task_ids_are_unique_and_use_task_namespace():
    first = new_task_id()
    second = new_task_id()

    assert first.startswith("tsk_")
    assert second.startswith("tsk_")
    assert len(first) == len("tsk_") + 26
    assert first != second


def test_project_resolution_is_read_only_for_known_unknown_archived_and_relocated_projects(tmp_path):
    vault = tmp_path / "vault"
    known_root = tmp_path / "known"
    moved_root = tmp_path / "moved"
    registry = ProjectRegistry(vault)
    record = registry.register(known_root, project_id="proj_known")

    known = resolve_project(vault, known_root)
    unknown = resolve_project(vault, tmp_path / "unknown")
    assert known.project_id == record["project_id"]
    assert known.status == "resolved"
    assert unknown.project_id is None
    assert unknown.status == "unresolved"
    assert len(registry.list_projects()) == 1

    registry.relocate("proj_known", moved_root)
    moved = resolve_project(vault, moved_root)
    assert moved.project_id == "proj_known"

    registry.set_status("proj_known", "archived")
    archived = resolve_project(vault, moved_root)
    assert archived.project_id == "proj_known"
    assert archived.status == "archived"


def test_project_resolution_refuses_corrupt_registry_instead_of_treating_it_as_unknown(tmp_path):
    vault = tmp_path / "vault"
    path = vault / ".claude" / "project-registry.json"
    path.parent.mkdir(parents=True)
    path.write_text("{not valid json", encoding="utf-8")

    with pytest.raises(TaskProjectResolutionError, match="unavailable"):
        resolve_project(vault, tmp_path / "project")


def test_task_analyzer_is_deterministic_for_turkish_planning_and_explicit_constraints(tmp_path):
    vault = tmp_path / "vault"
    project = tmp_path / "brain-eleven"
    ProjectRegistry(vault).register(project, project_id="brain-eleven")
    analyzer = TaskAnalyzer(vault, project)

    task = analyzer.analyze(
        "Phase 17 ContextRouter planını tasarla; Router ekleme ve production code'a dokunma.",
        task_id="tsk_01J00000000000000000000000",
        created_at="2026-09-03T12:00:00Z",
    )

    assert task.project.project_id == "brain-eleven"
    assert task.intent.value == "PLAN"
    assert task.operation.value == "design"
    assert task.requested_output.value == "implementation_plan"
    assert task.explicit_constraints == ("no_production_changes", "no_router")
    assert "phase-17" in task.entities
    assert "ContextRouter" in task.entities
    assert "architecture_change" in task.risk_flags


def test_task_analyzer_handles_english_debugging_and_unknown_project_without_side_effects(tmp_path):
    vault = tmp_path / "vault"
    analyzer = TaskAnalyzer(vault, tmp_path / "unknown")

    task = analyzer.analyze("Debug the API token migration error and add tests.")

    assert task.project.status == "unresolved"
    assert task.intent.value == "DEBUG"
    assert task.operation.value == "modify"
    assert {"security", "migration"} <= set(task.risk_flags)
    assert "project" in task.ambiguities
    assert ProjectRegistry(vault).list_projects() == []


def test_task_analyzer_does_not_match_intent_keywords_inside_larger_words(tmp_path):
    analyzer = TaskAnalyzer(tmp_path / "vault", tmp_path / "unknown")

    task = analyzer.analyze("Inspect the latest implementation.")

    assert task.intent.value == "REVIEW"


def test_task_analyzer_rejects_blank_and_accepts_large_valid_requests(tmp_path):
    analyzer = TaskAnalyzer(tmp_path / "vault", tmp_path / "unknown")
    with pytest.raises(TaskValidationError, match="must not be blank"):
        analyzer.analyze("  ")

    task = analyzer.analyze("Explain " + ("x" * 50_000))
    assert task.intent.value == "EXPLAIN"
