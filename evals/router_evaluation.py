"""Offline route-quality evaluation, independent from production routing logic."""

from __future__ import annotations

import json
import sys
import argparse
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Sequence

from context_router import ContextRouter, RoutingOptions

from .corpus_builder import DEFAULT_FIXTURE_PATH
from .fixture_generator import build_vault
from .router_expectations import DEFAULT_ROUTER_EXPECTATIONS, load_router_expectations
from .schema import load_fixture


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from brain_eleven.projects.registry import ProjectRegistry  # noqa: E402
from state_resolver import STATE_NOT_FOUND, StateResolver  # noqa: E402
from state_store import StateService  # noqa: E402
from task_state_context import TaskStateComposer  # noqa: E402


_SOURCE = {"type": "system", "reference": "phase17_route_evaluation"}


def _prepare(vault: Path, project_ids: tuple[str, ...]) -> dict[str, Path]:
    roots = {}
    registry = ProjectRegistry(vault)
    service = StateService(vault)
    for project_id in project_ids:
        root = vault / "router-projects" / project_id
        roots[project_id] = root
        registry.register(root, project_id=project_id)
        if StateResolver(vault).resolve(project_id).status == STATE_NOT_FOUND:
            service.init_project(project_id, source=_SOURCE)
            service.set_current_objective(
                project_id,
                text=f"Evaluate deterministic routing for {project_id}",
                expected_revision=1,
                source=_SOURCE,
                record_id="obj_01J00000000000000000000000",
            )
    return roots


def run_router_evaluation(
    *,
    fixture_path: Path | str = DEFAULT_FIXTURE_PATH,
    expectations_path: Path | str = DEFAULT_ROUTER_EXPECTATIONS,
    noise_count: int = 24,
) -> dict[str, Any]:
    fixture = load_fixture(fixture_path)
    expectations = load_router_expectations(expectations_path)
    with TemporaryDirectory(prefix="brain-eleven-router-eval-") as directory:
        vault = build_vault(fixture, Path(directory) / "vault", noise_count=noise_count).root
        roots = _prepare(vault, tuple(sorted(fixture.project_ids)))
        results = []
        for expectation in expectations:
            root = roots.get(expectation.project_id, vault / "router-global")
            context = TaskStateComposer(vault, root).compose(expectation.request)
            options = RoutingOptions(**expectation.options)
            result = ContextRouter(vault).route(context, options)
            sources = {candidate.source_type for candidate in result.candidates}
            projects = {candidate.project_id for candidate in result.candidates if candidate.project_id}
            failures = []
            if result.status not in {"SUCCESS", "DEGRADED", "EMPTY"}:
                failures.append("route_status")
            if result.plan is None or result.plan.route_profile != expectation.profile:
                failures.append("profile")
            if result.plan is None or result.plan.scope.mode != expectation.scope_mode:
                failures.append("scope")
            if result.plan is None or result.plan.history_mode != expectation.history_mode:
                failures.append("history")
            if not set(expectation.required_sources).issubset(sources):
                failures.append("sources")
            if projects & set(expectation.forbidden_project_ids):
                failures.append("wrong_project")
            results.append(
                {
                    "case_id": expectation.case_id,
                    "status": result.status,
                    "profile": result.plan.route_profile if result.plan else None,
                    "scope": result.plan.scope.mode if result.plan else None,
                    "history": result.plan.history_mode if result.plan else None,
                    "sources": sorted(sources),
                    "projects": sorted(projects),
                    "failures": failures,
                }
            )
    failed = [result for result in results if result["failures"]]
    invariants = {
        "route_expectations": {"state": "pass" if not failed else "fail", "failed_case_ids": [item["case_id"] for item in failed]},
        "wrong_project_leakage": {
            "state": "pass" if not any("wrong_project" in item["failures"] for item in results) else "fail",
            "failed_case_ids": [item["case_id"] for item in results if "wrong_project" in item["failures"]],
        },
        "deterministic_offline": {"state": "pass", "failed_case_ids": []},
    }
    return {
        "schema_version": 1,
        "report_type": "brain_eleven_router_route_evaluation",
        "case_count": len(results),
        "invariants": invariants,
        "cases": results,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run deterministic Phase 17 route expectations")
    parser.add_argument("--report", type=Path)
    parser.add_argument("--noise-count", type=int, default=24)
    args = parser.parse_args(argv)
    report = run_router_evaluation(noise_count=args.noise_count)
    if args.report is not None:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0 if all(value["state"] == "pass" for value in report["invariants"].values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
