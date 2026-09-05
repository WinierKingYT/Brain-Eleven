"""Offline deterministic evaluation for Phase 18 metadata-first resolution."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Mapping, Sequence

from authority import AuthorityOptions, AuthorityResolver
from context_router import ContextRouter, RoutingOptions

from .authority.corpus import expectations, validate_corpus
from .authority.schema import AuthorityExpectation


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from brain_eleven.projects.registry import ProjectRegistry  # noqa: E402
from brain_eleven.state import StateService  # noqa: E402
from task_state_context import TaskStateComposer  # noqa: E402


NOW = "2026-09-03T12:00:00Z"
SOURCE = {"type": "user", "reference": "phase18_eval"}
REPORT_TYPE = "brain_eleven_authority_evaluation"


def _memory(memory_id: str, project_id: str | None, topic: str, *, status: str = "active", fingerprint: str | None = None, superseded_by: str = "", source: str = "eval", timestamp: str = NOW) -> dict[str, Any]:
    scope = "project" if project_id else "global"
    return {
        "memory_id": memory_id, "type": "decision", "content": f"{topic} canonical decision.",
        "confidence": 0.9, "quality_score": 0.9, "source": source, "timestamp": timestamp,
        "related_notes": [], "section": "eval", "issues": [], "novelty": 1.0, "is_approved": True,
        "status": status, "resolved_at": "" if status == "active" else NOW,
        "resolved_by": "" if status == "active" else "eval", "resolution_note": "",
        "superseded_by": superseded_by, "supersession_note": "",
        "dedup_fingerprint": fingerprint or f"fp-{memory_id}", "scope": scope,
        "project": project_id or "", "project_label": project_id or "", "project_id": project_id or "",
    }


def _write_memory(vault: Path, records: list[dict[str, Any]]) -> None:
    path = vault / ".claude" / "validated-memory.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "schema_version": 2, "revision": 1, "updated_at": NOW, "validated_at": NOW,
        "summary": {}, "validated_memory": records, "rejected_memory": [],
    }), encoding="utf-8")


def _configured_vault(vault: Path, case: AuthorityExpectation) -> tuple[Path, StateService, str, dict[str, str], RoutingOptions]:
    project_a, project_b = vault / "project-a", vault / "project-b"
    registry = ProjectRegistry(vault)
    registry.register(project_a, project_id="project-a")
    registry.register(project_b, project_id="project-b")
    state = StateService(vault)
    state.init_project("project-a", source=SOURCE, now=NOW)
    state.init_project("project-b", source=SOURCE, now=NOW)
    state.set_current_objective(
        "project-a", text=f"Complete {case.case_id}", expected_revision=1,
        source=SOURCE, record_id="obj_01J00000000000000000000000", now=NOW,
    )
    topic = case.case_id.replace("_", " ")
    ids = {"new": "mem_new", "old": "mem_old", "first": "mem_first", "second": "mem_second", "foreign": "mem_foreign", "global": "mem_global", "unknown": "mem_unknown"}
    records: list[dict[str, Any]]
    routing = RoutingOptions()
    if case.category == "supersession":
        records = [
            _memory(ids["old"], "project-a", topic, status="superseded", superseded_by=ids["new"]),
            _memory(ids["new"], "project-a", topic),
        ]
        routing = RoutingOptions(history_mode="ACTIVE_PLUS_RELEVANT_HISTORY")
    elif case.category == "duplicate":
        records = [
            _memory(ids["first"], "project-a", topic, fingerprint="shared-fingerprint", timestamp="2026-09-02T12:00:00Z"),
            _memory(ids["second"], "project-a", topic, fingerprint="shared-fingerprint", timestamp=NOW),
        ]
    elif case.category == "scope_isolation":
        records = [
            _memory("mem_local", "project-a", topic), _memory(ids["foreign"], "project-b", topic),
            _memory(ids["global"], None, topic),
        ]
    elif case.category == "lifecycle":
        records = [_memory("mem_historical", "project-a", topic, status="resolved")]
        routing = RoutingOptions(history_mode="ACTIVE_PLUS_RELEVANT_HISTORY")
    elif case.category == "implementation_gap":
        records = [
            _memory(ids["old"], "project-a", topic, status="superseded", superseded_by=ids["new"]),
            _memory(ids["new"], "project-a", topic),
        ]
        routing = RoutingOptions(history_mode="ACTIVE_PLUS_RELEVANT_HISTORY")
    elif case.category == "incomplete_provenance":
        records = [_memory(ids["unknown"], "project-a", topic, source="")]
    elif case.category == "state_current":
        records = []
    else:  # determinism
        records = [_memory("mem_deterministic", "project-a", topic)]
    _write_memory(vault, records)
    if case.category == "implementation_gap":
        state.add_blocker(
            "project-a", text="Implementation remains stale", severity="HIGH", expected_revision=2,
            source=SOURCE, record_id="blk_01J00000000000000000000000", memory_ref=ids["old"], now=NOW,
        )
    return project_a, state, topic, ids, routing


def _authority_options(routing: RoutingOptions) -> AuthorityOptions:
    return AuthorityOptions(
        scope_mode=routing.scope_mode, selected_project_ids=routing.selected_project_ids,
        include_global=routing.include_global, history_mode=routing.history_mode, mode=routing.mode,
    )


def _has_content(value: Any) -> bool:
    if isinstance(value, Mapping):
        return "content" in value or any(_has_content(item) for item in value.values())
    if isinstance(value, list):
        return any(_has_content(item) for item in value)
    return False


def _stable_resolution(result: Any) -> dict[str, Any]:
    """Telemetry can report a cache hit; policy decisions must remain identical."""
    document = result.to_dict()
    document.pop("telemetry", None)
    return document


def _run_case(root: Path, case: AuthorityExpectation) -> dict[str, Any]:
    vault = root / case.case_id
    project_root, _state, topic, ids, routing = _configured_vault(vault, case)
    context = TaskStateComposer(vault, project_root).compose(f"Implement {topic}.")
    router = ContextRouter(vault)
    router_result = router.route(context, routing)
    memory_path = vault / ".claude" / "validated-memory.json"
    state_path = vault / ".claude" / "project-state.json"
    before = (hashlib.sha256(memory_path.read_bytes()).hexdigest(), hashlib.sha256(state_path.read_bytes()).hexdigest())
    resolver = AuthorityResolver(vault)
    result = resolver.resolve(context, router_result, _authority_options(routing))
    second = resolver.resolve(context, router_result, _authority_options(routing))
    after = (hashlib.sha256(memory_path.read_bytes()).hexdigest(), hashlib.sha256(state_path.read_bytes()).hexdigest())
    statuses = {item.candidate_id: item.status for item in result.candidates}
    expected = case.expected_statuses
    checks: dict[str, bool] = {
        "status": result.status in {"SUCCESS", "DEGRADED", "EMPTY"},
        "canonical_write": before == after,
        "deterministic": _stable_resolution(result) == _stable_resolution(second),
        "content_safe": not _has_content(result.to_dict()) and "retrieval_score" not in json.dumps(result.to_dict()),
        "wrong_project": all(item.project_id != "project-b" for item in result.candidates),
    }
    candidate_projects = {item.candidate_id: item.project_id for item in result.candidates}
    checks["cross_project_compare"] = all(
        len({candidate_projects.get(candidate_id) for candidate_id in conflict.candidate_ids if candidate_projects.get(candidate_id)}) <= 1
        for conflict in result.conflict_sets
    )
    if case.category == "supersession":
        checks["expectation"] = statuses.get(ids["old"]) == expected["old"] and statuses.get(ids["new"]) == expected["new"]
    elif case.category == "duplicate":
        checks["expectation"] = statuses.get(ids["first"]) == expected["first"] and statuses.get(ids["second"]) == expected["second"]
    elif case.category == "scope_isolation":
        checks["expectation"] = ids["foreign"] not in statuses
    elif case.category == "lifecycle":
        checks["expectation"] = statuses.get("mem_historical") == expected["historical"]
    elif case.category == "implementation_gap":
        checks["expectation"] = statuses.get(ids["old"]) == expected["old"] and any(item.status == expected["blocker"] for item in result.candidates if item.source_type == "state")
    elif case.category == "incomplete_provenance":
        checks["expectation"] = statuses.get(ids["unknown"]) == expected["unknown"]
    elif case.category == "state_current":
        checks["expectation"] = any(item.status == expected["objective"] for item in result.candidates if item.source_type == "state")
    else:
        checks["expectation"] = checks["deterministic"]
    return {
        "case_id": case.case_id, "category": case.category, "status": result.status,
        "candidate_ids": sorted(statuses), "conflict_kinds": sorted(conflict.kind for conflict in result.conflict_sets),
        "checks": checks,
    }


def run_authority_evaluation(*, suite: str = "smoke") -> dict[str, Any]:
    corpus = validate_corpus()
    cases = expectations(suite)
    with TemporaryDirectory(prefix="brain-eleven-authority-eval-") as directory:
        results = [_run_case(Path(directory), case) for case in cases]
    invariant_names = ("canonical_write", "deterministic", "content_safe", "wrong_project", "cross_project_compare")
    invariants = {
        name: {"state": "pass" if all(row["checks"][name] for row in results) else "fail", "violations": sum(not row["checks"][name] for row in results)}
        for name in invariant_names
    }
    expectations_passed = sum(row["checks"]["expectation"] for row in results)
    return {
        "schema_version": 1, "report_type": REPORT_TYPE, "provider": "metadata_authority_v1",
        "rollout_mode": "SHADOW", "context_injection": False, "suite": suite,
        "case_count": len(results), "corpus": corpus, "expectations_passed": expectations_passed,
        "invariants": invariants, "cases": results,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run deterministic Phase 18 authority evaluation")
    parser.add_argument("--suite", choices=("smoke", "public", "holdout", "all"), default="smoke")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    report = run_authority_evaluation(suite=args.suite)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"suite": args.suite, "case_count": report["case_count"], "invariants": report["invariants"]}, sort_keys=True))
    return 0 if report["expectations_passed"] == report["case_count"] and all(item["state"] == "pass" for item in report["invariants"].values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
