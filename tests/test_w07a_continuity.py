"""Focused W-07A tests for native structured SessionStart continuity."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace

from brain_eleven.runtime.context import compile_bootstrap
from brain_eleven.projects.registry import ProjectRegistry
from brain_eleven.state import StateService, StateStore
from tests.test_pre13_runtime import runtime  # noqa: F401 - fixture registration


_COMPILER_PATH = Path(__file__).parents[1] / "scripts" / "context-compiler.py"
_SPEC = importlib.util.spec_from_file_location("w07a_context_compiler", _COMPILER_PATH)
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)
ContextCompiler = _MODULE.ContextCompiler


def _state(*, work_items=(), requirements=(), blockers=(), constraints=(), risks=()):
    return SimpleNamespace(
        status=_MODULE.STATE_AVAILABLE,
        current={
            "phase_id": "phase-20",
            "milestone": {"title": "Continuity hardening"},
            "objective": {"text": "Keep native bootstrap useful"},
        },
        active_work_items=work_items,
        active_requirements=requirements,
        active_blockers=blockers,
        constraints=constraints,
        risks=risks,
    )


def _add_state_records(vault, project_id):
    service = StateService(vault)
    source = {"type": "user", "reference": "w07a-test"}

    def revision():
        return StateStore(vault).project_revision(project_id)

    service.add_work_item(
        project_id,
        text="Finish native continuity read",
        expected_revision=revision(),
        source=source,
        record_id="wrk_w07a",
    )
    service.add_requirement(
        project_id,
        text="Keep state project scoped",
        expected_revision=revision(),
        source=source,
        record_id="req_w07a",
    )
    service.add_blocker(
        project_id,
        text="Bootstrap continuity needs bounded output",
        severity="HIGH",
        expected_revision=revision(),
        source=source,
        record_id="blk_w07a",
    )
    service.add_constraint(
        project_id,
        text="No markdown writer",
        expected_revision=revision(),
        source=source,
        record_id="con_w07a",
    )
    service.add_risk(
        project_id,
        text="Large state can waste hook budget",
        severity="MEDIUM",
        expected_revision=revision(),
        source=source,
        record_id="rsk_w07a",
    )


def test_structured_continuity_renders_all_categories_with_stable_limits(tmp_path):
    compiler = ContextCompiler(str(tmp_path))
    long_text = "x" * 200
    state = _state(
        work_items=tuple(
            {"id": f"wrk_{index}", "text": f"work item {index}"}
            for index in reversed(range(5))
        ),
        requirements=({"id": "req_1", "text": "Keep requirements visible"},),
        blockers=({"id": "blk_1", "text": "A blocker", "severity": "HIGH"},),
        constraints=({"id": "con_1", "text": "SQLite only"},),
        risks=(
            {"id": "rsk_1", "text": "A risk", "severity": "LOW"},
            {"id": "rsk_2", "text": long_text, "severity": "LOW"},
        ),
    )

    rendered = compiler._generate_context_block([], {}, "", "", state)

    assert "Active work items:" in rendered
    assert "[WORK_ITEM] work item 0" in rendered
    assert "[WORK_ITEM] work item 1" in rendered
    assert "[WORK_ITEM] work item 2" in rendered
    assert "[WORK_ITEM] work item 3" not in rendered
    assert "[REQUIREMENT] Keep requirements visible" in rendered
    assert "[BLOCKER] [HIGH] A blocker" in rendered
    assert "[CONSTRAINT] SQLite only" in rendered
    assert "[RISK] [LOW] A risk" in rendered
    assert long_text not in rendered
    assert "x" * 160 in rendered


def test_malformed_optional_continuity_records_are_skipped(tmp_path):
    compiler = ContextCompiler(str(tmp_path))
    state = _state(
        work_items=(None, {"id": "missing-text"}, {"id": "valid", "text": "valid work"}),
        requirements="not-a-sequence",
        blockers=({"text": 42},),
        constraints=({"title": "title fallback"},),
        risks=(),
    )

    rendered = compiler._generate_context_block([], {}, "", "", state)

    assert "valid work" in rendered
    assert "title fallback" in rendered
    assert "missing-text" not in rendered
    assert "not-a-sequence" not in rendered
    assert "42" not in rendered


def test_empty_state_does_not_fabricate_continuity(tmp_path):
    compiler = ContextCompiler(str(tmp_path))

    rendered = compiler._generate_context_block([], {}, "", "", None)

    assert "CURRENT PROJECT STATE" not in rendered
    assert "Active work items" not in rendered
    assert "Active requirements" not in rendered


def test_native_bootstrap_reads_only_resolved_project_state(runtime, tmp_path):
    vault, project_id = runtime
    _add_state_records(vault, project_id)

    other_root = tmp_path / "other-project"
    other_root.mkdir()
    other = ProjectRegistry(vault).register(other_root, project_id="other-project")
    StateService(vault).init_project(other["project_id"], source={"type": "user", "reference": "w07a-test"})
    StateService(vault).add_requirement(
        other["project_id"],
        text="FOREIGN PROJECT MUST NEVER APPEAR",
        expected_revision=StateStore(vault).project_revision(other["project_id"]),
        source={"type": "user", "reference": "w07a-test"},
        record_id="req_foreign",
    )

    companion = vault / "🔮 Companion"
    companion.mkdir(exist_ok=True)
    for filename in ("Last Session.md", "Threads.md", "Daily.md", "Açık Döngüler.md"):
        (companion / filename).write_text("UNSCOPED MARKDOWN MUST NOT APPEAR", encoding="utf-8")

    result = compile_bootstrap(vault, vault)

    assert result["status"] == "SUCCESS"
    assert "Finish native continuity read" in result["context"]
    assert "Keep state project scoped" in result["context"]
    assert "Bootstrap continuity needs bounded output" in result["context"]
    assert "No markdown writer" in result["context"]
    assert "Large state can waste hook budget" in result["context"]
    assert "FOREIGN PROJECT MUST NEVER APPEAR" not in result["context"]
    assert "UNSCOPED MARKDOWN MUST NOT APPEAR" not in result["context"]
