"""Offline deterministic Phase 16 task-and-state evaluation harness."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Mapping, Sequence


_ROOT = Path(__file__).resolve().parents[1]
_SCRIPTS_DIRECTORY = _ROOT / "scripts"
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
if str(_SCRIPTS_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIRECTORY))

from brain_eleven.projects.registry import ProjectRegistry
from brain_eleven.memory import MemoryStore
from brain_eleven.state.resolver import StateResolver
from brain_eleven.state import StateService
from task_model import TaskAnalyzer


TASK_STATE_EVAL_SCHEMA_VERSION = 1
TASK_STATE_EVAL_PROVIDER = "task_state_v1"
SUITES = {"smoke": ("test",), "public": ("dev", "test"), "holdout": ("holdout",), "all": ("dev", "test", "holdout")}
SOURCE = {"type": "user", "reference": "phase16-evaluation"}
NOW = "2026-09-03T12:00:00Z"
STALE_NOW = datetime(2026, 10, 4, tzinfo=timezone.utc)


@dataclass(frozen=True)
class TaskCase:
    case_id: str
    suite: str
    request: str
    project_status: str
    expected_intent: str
    expected_constraints: tuple[str, ...] = ()
    expected_risks: tuple[str, ...] = ()


@dataclass(frozen=True)
class StateCase:
    case_id: str
    suite: str
    scenario: str
    expected: Mapping[str, Any]


_TASK_CASES = (
    TaskCase("task_plan_tr", "test", "Phase 17 planını hazırla.", "resolved", "PLAN"),
    TaskCase("task_plan_en", "test", "Plan the next architecture phase.", "resolved", "PLAN"),
    TaskCase("task_review", "test", "Son commiti incele.", "resolved", "REVIEW"),
    TaskCase("task_debug", "test", "Debug the current error.", "resolved", "DEBUG"),
    TaskCase("task_migrate", "test", "SQLite migration uygula.", "resolved", "MIGRATE", expected_risks=("migration",)),
    TaskCase("task_test", "test", "StateStore test et.", "resolved", "TEST"),
    TaskCase("task_research", "test", "Context router hakkında araştır.", "resolved", "RESEARCH"),
    TaskCase("task_explain", "test", "Task modelini açıkla.", "resolved", "EXPLAIN"),
    TaskCase("task_design", "test", "State resolver mimarisini tasarla.", "resolved", "DESIGN", expected_risks=("architecture_change",)),
    TaskCase("task_operate", "test", "Deployment izleme işlemini çalıştır.", "resolved", "OPERATE", expected_risks=("external_dependency",)),
    TaskCase("task_implement", "test", "Typed transition ekle.", "resolved", "IMPLEMENT"),
    TaskCase("task_unknown_intent", "test", "Bununla ilgilen.", "resolved", "UNKNOWN"),
    TaskCase("task_archived", "test", "Archived geçmişini planla.", "archived", "PLAN"),
    TaskCase("task_unknown_project", "test", "Explain the task state model.", "unresolved", "EXPLAIN"),
    TaskCase("task_no_router", "test", "Router ekleme; Phase 17 planını hazırla.", "resolved", "PLAN", expected_constraints=("no_router",)),
    TaskCase("task_no_production", "test", "Production code'a dokunma; state planını tasarla.", "resolved", "PLAN", expected_constraints=("no_production_changes",)),
    TaskCase("task_offline", "test", "Internet kullanma, offline değerlendirme planla.", "resolved", "PLAN", expected_constraints=("offline_only",), expected_risks=("external_dependency",)),
    TaskCase("task_cross_project", "test", "Başka proje için cross-project state incele.", "resolved", "REVIEW", expected_risks=("cross_project",)),
    TaskCase("task_security", "test", "API token auth bugını düzelt.", "resolved", "DEBUG", expected_risks=("security",)),
    TaskCase("task_destructive", "test", "Canonical memory store'u silme riskini incele.", "resolved", "REVIEW", expected_risks=("destructive_change", "canonical_store")),
    TaskCase("task_dev_unicode", "dev", "Türkçe görev durumunu açıkla.", "resolved", "EXPLAIN"),
    TaskCase("task_dev_constraints", "dev", "No commit, no push; planla.", "resolved", "PLAN", expected_constraints=("no_commit_or_push",)),
    TaskCase("task_dev_migration", "dev", "Schema migration test et.", "resolved", "MIGRATE", expected_risks=("migration",)),
    TaskCase("task_dev_design", "dev", "TaskStateContext contract tasarla.", "resolved", "DESIGN", expected_risks=("architecture_change",)),
    TaskCase("task_holdout_review", "holdout", "Inspect the latest implementation.", "resolved", "REVIEW"),
    TaskCase("task_holdout_debug", "holdout", "Hafıza hatasını debug et.", "resolved", "DEBUG"),
    TaskCase("task_holdout_unknown", "holdout", "Belirsiz isteği ele al.", "unresolved", "UNKNOWN"),
    TaskCase("task_holdout_risk", "holdout", "Secret token migration planla.", "resolved", "PLAN", expected_risks=("security", "migration")),
)

_STATE_CASES = (
    StateCase("state_available", "test", "available", {"status": "AVAILABLE"}),
    StateCase("state_missing", "test", "missing", {"status": "STATE_NOT_FOUND"}),
    StateCase("state_unknown", "test", "unknown", {"status": "PROJECT_UNKNOWN"}),
    StateCase("state_archived", "test", "archived", {"status": "PROJECT_ARCHIVED"}),
    StateCase("state_corrupt", "test", "corrupt", {"status": "STATE_CORRUPT"}),
    StateCase("state_stale", "test", "stale", {"status": "AVAILABLE", "freshness": "stale_candidate"}),
    StateCase("state_active_phase", "test", "active_phase", {"status": "AVAILABLE", "phase": "phase-16"}),
    StateCase("state_completed_phase", "test", "completed_phase", {"status": "AVAILABLE", "phase": None}),
    StateCase("state_active_requirement", "test", "active_requirement", {"status": "AVAILABLE", "requirements": 1}),
    StateCase("state_resolved_requirement", "test", "resolved_requirement", {"status": "AVAILABLE", "requirements": 0}),
    StateCase("state_todo_work", "test", "todo_work", {"status": "AVAILABLE", "work_items": 1}),
    StateCase("state_done_work", "test", "done_work", {"status": "AVAILABLE", "work_items": 0}),
    StateCase("state_active_blocker", "test", "active_blocker", {"status": "AVAILABLE", "blockers": 1}),
    StateCase("state_resolved_blocker", "test", "resolved_blocker", {"status": "AVAILABLE", "blockers": 0}),
    StateCase("state_constraint", "test", "constraint", {"status": "AVAILABLE", "constraints": 1}),
    StateCase("state_risk", "test", "risk", {"status": "AVAILABLE", "risks": 1}),
    StateCase("state_other_project", "test", "other_project", {"status": "STATE_NOT_FOUND"}),
    StateCase("state_dangling_reference", "test", "dangling_reference", {"status": "AVAILABLE", "dangling": 1}),
    StateCase("state_wrong_project_reference", "test", "wrong_project_reference", {"status": "AVAILABLE", "wrong_project": 1}),
    StateCase("state_global_reference", "test", "global_reference", {"status": "AVAILABLE", "valid": 1}),
    StateCase("state_dev_phase", "dev", "active_phase", {"status": "AVAILABLE", "phase": "phase-16"}),
    StateCase("state_dev_blocker", "dev", "active_blocker", {"status": "AVAILABLE", "blockers": 1}),
    StateCase("state_dev_resolved", "dev", "resolved_requirement", {"status": "AVAILABLE", "requirements": 0}),
    StateCase("state_dev_global", "dev", "global_reference", {"status": "AVAILABLE", "valid": 1}),
    StateCase("state_holdout_archived", "holdout", "archived", {"status": "PROJECT_ARCHIVED"}),
    StateCase("state_holdout_corrupt", "holdout", "corrupt", {"status": "STATE_CORRUPT"}),
    StateCase("state_holdout_dangling", "holdout", "dangling_reference", {"status": "AVAILABLE", "dangling": 1}),
    StateCase("state_holdout_unknown", "holdout", "unknown", {"status": "PROJECT_UNKNOWN"}),
)


class TaskStateEvaluationError(ValueError):
    """Raised when the deterministic Phase 16 harness cannot run safely."""


def _cases_for_suite(cases, suite: str):
    if suite not in SUITES:
        raise TaskStateEvaluationError(f"unsupported evaluation suite: {suite}")
    selected = tuple(case for case in cases if case.suite in SUITES[suite])
    if not selected:
        raise TaskStateEvaluationError(f"empty evaluation suite: {suite}")
    return selected


def _project_for_task(vault: Path, case: TaskCase) -> Path:
    project = vault / "brain-eleven"
    registry = ProjectRegistry(vault)
    if case.project_status != "unresolved":
        registry.register(project, project_id="brain-eleven")
        if case.project_status == "archived":
            registry.set_status("brain-eleven", "archived")
    return project if case.project_status != "unresolved" else vault / "unknown"


def _evaluate_task_case(root: Path, case: TaskCase) -> dict[str, Any]:
    project_root = _project_for_task(root, case)
    task = TaskAnalyzer(root, project_root).analyze(
        case.request,
        task_id="tsk_01J00000000000000000000000",
        created_at=NOW,
    )
    failures = []
    if task.project.status != case.project_status:
        failures.append("project_resolution")
    if task.intent.value != case.expected_intent:
        failures.append("intent")
    if not set(case.expected_constraints) <= set(task.explicit_constraints):
        failures.append("explicit_constraints")
    if not set(case.expected_risks) <= set(task.risk_flags):
        failures.append("risk_flags")
    return {
        "case_id": case.case_id,
        "project_status": task.project.status,
        "intent": task.intent.value,
        "constraints": list(task.explicit_constraints),
        "risk_flags": list(task.risk_flags),
        "failures": failures,
    }


def _register_projects(vault: Path) -> None:
    registry = ProjectRegistry(vault)
    registry.register(vault / "brain", project_id="brain-eleven")
    registry.register(vault / "other", project_id="other-project")


def _init_service(vault: Path, *, now: str = NOW) -> StateService:
    _register_projects(vault)
    service = StateService(vault)
    service.init_project("brain-eleven", source=SOURCE, now=now)
    return service


def _append_reference_without_authority(service: StateService, memory_id: str) -> None:
    def mutate(project):
        project["references"]["memory_ids"].append(memory_id)
    service.store._transact_project(
        "brain-eleven",
        expected_revision=1,
        operation="fixture_reference_injected",
        source=SOURCE,
        record_ids=[memory_id],
        mutator=mutate,
        now=NOW,
    )


def _memory(memory_id: str, *, scope: str, project_id: str | None = None) -> dict[str, Any]:
    record = {
        "memory_id": memory_id,
        "content": "Synthetic evaluation reference.",
        "type": "decision",
        "status": "active",
        "scope": scope,
    }
    if project_id is not None:
        record["project_id"] = project_id
    return record


def _evaluate_state_case(root: Path, case: StateCase) -> dict[str, Any]:
    target_project = "brain-eleven"
    resolver_now = None
    if case.scenario == "unknown":
        _register_projects(root)
        result = StateResolver(root).resolve("unknown")
    elif case.scenario == "missing":
        _register_projects(root)
        result = StateResolver(root).resolve(target_project)
    elif case.scenario == "corrupt":
        _register_projects(root)
        path = StateService(root).store.path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{not valid json", encoding="utf-8")
        result = StateResolver(root).resolve(target_project)
    elif case.scenario == "other_project":
        _register_projects(root)
        StateService(root).init_project("other-project", source=SOURCE, now=NOW)
        result = StateResolver(root).resolve(target_project)
    else:
        service = _init_service(root, now="2020-01-01T00:00:00Z" if case.scenario == "stale" else NOW)
        revision = 1
        if case.scenario in {"active_phase", "completed_phase"}:
            service.set_current_milestone(
                target_project, phase_id="phase-16", title="Task + State Model",
                expected_revision=revision, source=SOURCE,
                record_id="mil_01J00000000000000000000000", now=NOW,
            )
            revision += 1
            if case.scenario == "completed_phase":
                service.transition_milestone(
                    target_project, milestone_id="mil_01J00000000000000000000000",
                    target_status="COMPLETED", expected_revision=revision, source=SOURCE, now=NOW,
                )
        elif case.scenario in {"active_requirement", "resolved_requirement"}:
            service.add_requirement(
                target_project, text="A synthetic requirement", expected_revision=revision, source=SOURCE,
                record_id="req_01J00000000000000000000000", now=NOW,
            )
            revision += 1
            if case.scenario == "resolved_requirement":
                service.resolve_requirement(
                    target_project, requirement_id="req_01J00000000000000000000000",
                    expected_revision=revision, source=SOURCE, now=NOW,
                )
        elif case.scenario in {"todo_work", "done_work"}:
            service.add_work_item(
                target_project, text="A synthetic work item", expected_revision=revision, source=SOURCE,
                record_id="wrk_01J00000000000000000000000", now=NOW,
            )
            revision += 1
            if case.scenario == "done_work":
                service.transition_work_item(
                    target_project, work_item_id="wrk_01J00000000000000000000000",
                    target_status="DONE", expected_revision=revision, source=SOURCE, now=NOW,
                )
        elif case.scenario in {"active_blocker", "resolved_blocker"}:
            service.add_blocker(
                target_project, text="A synthetic blocker", severity="HIGH", expected_revision=revision,
                source=SOURCE, record_id="blk_01J00000000000000000000000", now=NOW,
            )
            revision += 1
            if case.scenario == "resolved_blocker":
                service.resolve_blocker(
                    target_project, blocker_id="blk_01J00000000000000000000000",
                    expected_revision=revision, source=SOURCE, now=NOW,
                )
        elif case.scenario == "constraint":
            service.add_constraint(
                target_project, text="memory_foundation_frozen", expected_revision=revision,
                source=SOURCE, record_id="con_01J00000000000000000000000", now=NOW,
            )
        elif case.scenario == "risk":
            service.add_risk(
                target_project, text="Synthetic architecture risk", severity="MEDIUM",
                expected_revision=revision, source=SOURCE, record_id="rsk_01J00000000000000000000000", now=NOW,
            )
        elif case.scenario == "dangling_reference":
            _append_reference_without_authority(service, "mem_missing")
        elif case.scenario == "wrong_project_reference":
            MemoryStore(root).append(_memory("mem_other", scope="project", project_id="other-project"))
            _append_reference_without_authority(service, "mem_other")
        elif case.scenario == "global_reference":
            MemoryStore(root).append(_memory("mem_global", scope="global"))
            service.add_memory_reference(
                target_project, memory_id="mem_global", expected_revision=revision, source=SOURCE, now=NOW,
            )
        elif case.scenario == "archived":
            ProjectRegistry(root).set_status(target_project, "archived")
        elif case.scenario not in {"available", "stale"}:
            raise TaskStateEvaluationError(f"unsupported state scenario: {case.scenario}")
        resolver_now = STALE_NOW if case.scenario == "stale" else None
        result = StateResolver(root).resolve(target_project, now=resolver_now)

    expected = case.expected
    failures = []
    if result.status != expected["status"]:
        failures.append("state_status")
    checks = {
        "phase": result.current["phase_id"],
        "freshness": result.freshness["status"],
        "requirements": len(result.active_requirements),
        "work_items": len(result.active_work_items),
        "blockers": len(result.active_blockers),
        "constraints": len(result.constraints),
        "risks": len(result.risks),
        "valid": len(result.references["valid"]),
        "dangling": len(result.references["dangling"]),
        "wrong_project": len(result.references["wrong_project"]),
    }
    for name, expected_value in expected.items():
        if name != "status" and checks[name] != expected_value:
            failures.append(name)
    return {
        "case_id": case.case_id,
        "status": result.status,
        "phase": result.current["phase_id"],
        "freshness": result.freshness["status"],
        "counts": checks,
        "failures": failures,
    }


def _invariant(state: str, cases: Sequence[dict[str, Any]], failure_name: str) -> dict[str, Any]:
    failed = [case["case_id"] for case in cases if failure_name in case["failures"]]
    return {"state": "fail" if failed else state, "failed_case_ids": failed}


def run_task_state_evaluation(*, suite: str = "smoke") -> dict[str, Any]:
    """Run reproducible public task and state cases without network access."""
    task_cases = _cases_for_suite(_TASK_CASES, suite)
    state_cases = _cases_for_suite(_STATE_CASES, suite)
    with TemporaryDirectory(prefix="brain-eleven-task-state-eval-") as directory:
        root = Path(directory)
        task_results = [_evaluate_task_case(root / "tasks" / case.case_id, case) for case in task_cases]
        state_results = [_evaluate_state_case(root / "states" / case.case_id, case) for case in state_cases]
    task_failures = [case for case in task_results if case["failures"]]
    state_failures = [case for case in state_results if case["failures"]]
    invariants = {
        "task_project_resolution": _invariant("pass", task_results, "project_resolution"),
        "task_intent_accuracy": _invariant("pass", task_results, "intent"),
        "explicit_constraint_recall": _invariant("pass", task_results, "explicit_constraints"),
        "risk_flag_recall": _invariant("pass", task_results, "risk_flags"),
        "state_accuracy": {
            "state": "fail" if state_failures else "pass",
            "failed_case_ids": [case["case_id"] for case in state_failures],
        },
        "wrong_project_state_leakage": _invariant("pass", state_results, "wrong_project"),
        "resolved_item_leakage": {
            "state": "fail" if any(
                name in result["failures"] for result in state_results for name in ("requirements", "work_items", "blockers")
            ) else "pass",
            "failed_case_ids": [
                result["case_id"] for result in state_results
                if any(name in result["failures"] for name in ("requirements", "work_items", "blockers"))
            ],
        },
        "corruption_detection": {
            "state": "fail" if any(
                result["case_id"] in {"state_corrupt", "state_holdout_corrupt"}
                and "state_status" in result["failures"]
                for result in state_results
            ) else "pass",
            "failed_case_ids": [
                result["case_id"] for result in state_results
                if result["case_id"] in {"state_corrupt", "state_holdout_corrupt"}
                and "state_status" in result["failures"]
            ],
        },
    }
    return {
        "schema_version": TASK_STATE_EVAL_SCHEMA_VERSION,
        "report_type": "brain_eleven_task_state_evaluation",
        "provider": TASK_STATE_EVAL_PROVIDER,
        "suite": suite,
        "metrics": {
            "task_case_count": len(task_results),
            "state_case_count": len(state_results),
            "task_pass_rate": (len(task_results) - len(task_failures)) / len(task_results),
            "state_pass_rate": (len(state_results) - len(state_failures)) / len(state_results),
            "wrong_project_state_leakage_rate": sum(
                result["counts"]["wrong_project"] > 0 and result["case_id"] != "state_wrong_project_reference"
                for result in state_results
            ) / len(state_results),
        },
        "invariants": invariants,
        "task_cases": task_results,
        "state_cases": state_results,
    }


def _gate_failed(report: Mapping[str, Any]) -> bool:
    return any(invariant["state"] != "pass" for invariant in report["invariants"].values())


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run offline Phase 16 task/state evaluation.")
    parser.add_argument("--suite", default="smoke", choices=tuple(SUITES))
    parser.add_argument("--report", type=Path)
    arguments = parser.parse_args(argv)
    report = run_task_state_evaluation(suite=arguments.suite)
    if arguments.report is not None:
        arguments.report.parent.mkdir(parents=True, exist_ok=True)
        arguments.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "provider": report["provider"],
        "suite": report["suite"],
        "task_case_count": report["metrics"]["task_case_count"],
        "state_case_count": report["metrics"]["state_case_count"],
        "gate": "fail" if _gate_failed(report) else "pass",
    }, sort_keys=True))
    return 1 if _gate_failed(report) else 0


if __name__ == "__main__":
    raise SystemExit(main())
