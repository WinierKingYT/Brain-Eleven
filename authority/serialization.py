"""Strict JSON decoding for content-safe Authority CLI/cache contracts."""

from __future__ import annotations

from typing import Any, Mapping

from .models import (
    AUTHORITY_SCHEMA_VERSION,
    ClaimEnvelope,
    ConflictSet,
    ExplanationEntry,
    ResolutionCandidate,
    ResolutionResult,
)


def _mapping(value: Any, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{field} must be an object")
    return value


def _sequence(value: Any, field: str) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError(f"{field} must be an array")
    return value


def _contains_content(value: Any) -> bool:
    if isinstance(value, Mapping):
        return "content" in value or any(_contains_content(item) for item in value.values())
    if isinstance(value, list):
        return any(_contains_content(item) for item in value)
    return False


def resolution_result_from_dict(document: Mapping[str, Any]) -> ResolutionResult:
    """Decode a cached result and reject any accidental content persistence."""
    document = _mapping(document, "resolution")
    if document.get("schema_version") != AUTHORITY_SCHEMA_VERSION:
        raise ValueError("resolution schema_version must be 1")
    if _contains_content(document):
        raise ValueError("authority resolution must not persist content")
    candidates = []
    for value in _sequence(document.get("candidates", []), "resolution.candidates"):
        value = _mapping(value, "resolution.candidate")
        claim_data = _mapping(value.get("claim"), "resolution.candidate.claim")
        claim = ClaimEnvelope(
            candidate_id=claim_data["candidate_id"],
            claim_class=claim_data["claim_class"],
            project_id=claim_data.get("project_id"),
            scope=claim_data["scope"],
            lifecycle=claim_data["lifecycle"],
            provenance=claim_data["provenance"],
            dedup_fingerprint=claim_data.get("dedup_fingerprint"),
            superseded_by=claim_data.get("superseded_by"),
            state_kind=claim_data.get("state_kind"),
        )
        candidates.append(
            ResolutionCandidate(
                candidate_id=value["candidate_id"],
                source_type=value["source_type"],
                project_id=value.get("project_id"),
                canonical_ref=_mapping(value["canonical_ref"], "resolution.candidate.canonical_ref"),
                claim=claim,
                status=value["status"],
                action=value["action"],
                reason_codes=tuple(_sequence(value.get("reason_codes", []), "resolution.candidate.reason_codes")),
            )
        )
    conflicts = []
    for value in _sequence(document.get("conflict_sets", []), "resolution.conflict_sets"):
        value = _mapping(value, "resolution.conflict")
        conflicts.append(
            ConflictSet(
                conflict_id=value["conflict_id"],
                kind=value["kind"],
                candidate_ids=tuple(_sequence(value["candidate_ids"], "resolution.conflict.candidate_ids")),
                action=value["action"],
                reason_codes=tuple(_sequence(value.get("reason_codes", []), "resolution.conflict.reason_codes")),
            )
        )
    ledger = []
    for value in _sequence(document.get("ledger", []), "resolution.ledger"):
        value = _mapping(value, "resolution.ledger_entry")
        ledger.append(
            ExplanationEntry(
                subject_ids=tuple(_sequence(value["subject_ids"], "resolution.ledger_entry.subject_ids")),
                code=value["code"],
                action=value["action"],
            )
        )
    return ResolutionResult(
        status=document["status"],
        policy_version=document["policy_version"],
        input_revisions=_mapping(document.get("input_revisions"), "resolution.input_revisions"),
        candidates=tuple(candidates),
        conflict_sets=tuple(conflicts),
        ledger=tuple(ledger),
        degraded_reasons=tuple(_sequence(document.get("degraded_reasons", []), "resolution.degraded_reasons")),
        error=document.get("error"),
        telemetry=_mapping(document.get("telemetry", {}), "resolution.telemetry"),
    )


def task_state_from_dict(document: Mapping[str, Any]):
    """Decode task/state input, then rely on canonical reads for truth."""
    import sys
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    scripts = root / "scripts"
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    from state_resolver import CurrentProjectState
    from task_model import TaskEnvelope
    from task_state_context import TASK_STATE_CONTEXT_SCHEMA_VERSION, TaskStateContext

    document = _mapping(document, "task_state")
    if document.get("schema_version") != TASK_STATE_CONTEXT_SCHEMA_VERSION:
        raise ValueError("task_state schema_version is unsupported")
    task = TaskEnvelope.from_dict(_mapping(document.get("task"), "task_state.task"))
    state_data = _mapping(document.get("state"), "task_state.state")
    required = {
        "project_id", "status", "state_revision", "updated_at", "freshness", "current",
        "active_requirements", "active_work_items", "active_blockers", "constraints", "risks",
        "references", "error", "archived",
    }
    if set(state_data) != required:
        raise ValueError("task_state.state fields are invalid")
    project_id = state_data["project_id"]
    if project_id is not None and (not isinstance(project_id, str) or not project_id):
        raise ValueError("task_state.state.project_id is invalid")
    revision = state_data["state_revision"]
    if revision is not None and (isinstance(revision, bool) or not isinstance(revision, int) or revision < 0):
        raise ValueError("task_state.state.state_revision is invalid")
    def records(name: str) -> tuple[Mapping[str, Any], ...]:
        return tuple(_mapping(value, f"task_state.state.{name}") for value in _sequence(state_data[name], f"task_state.state.{name}"))
    return TaskStateContext(
        task=task,
        state=CurrentProjectState(
            project_id=project_id,
            status=state_data["status"],
            state_revision=revision,
            updated_at=state_data["updated_at"],
            freshness=_mapping(state_data["freshness"], "task_state.state.freshness"),
            current=_mapping(state_data["current"], "task_state.state.current"),
            active_requirements=records("active_requirements"),
            active_work_items=records("active_work_items"),
            active_blockers=records("active_blockers"),
            constraints=records("constraints"),
            risks=records("risks"),
            references=_mapping(state_data["references"], "task_state.state.references"),
            error=state_data["error"],
            archived=state_data["archived"],
        ),
    )


def router_result_from_dict(document: Mapping[str, Any]):
    """Decode the existing Phase 17 content-free RouterResult contract."""
    from context_router.models import Candidate, RetrievalPlan, RetrievalQuery, RouteScope, RouterResult

    document = _mapping(document, "router_result")
    if document.get("schema_version") != 1:
        raise ValueError("router_result schema_version is unsupported")
    plan_data = _mapping(document.get("plan"), "router_result.plan")
    scope_data = _mapping(plan_data.get("scope"), "router_result.plan.scope")
    scope = RouteScope(
        mode=scope_data["mode"],
        project_ids=tuple(_sequence(scope_data["project_ids"], "router_result.plan.scope.project_ids")),
        include_global=scope_data["include_global"],
    )
    queries = tuple(
        RetrievalQuery(
            query_id=value["query_id"],
            source=value["source"],
            strategy=value["strategy"],
            terms=tuple(_sequence(value.get("terms", []), "router_result.plan.query.terms")),
            memory_types=tuple(_sequence(value.get("memory_types", []), "router_result.plan.query.memory_types")),
            pass_name=value.get("pass", "strict"),
        )
        for value in _sequence(plan_data.get("queries", []), "router_result.plan.queries")
        for value in (_mapping(value, "router_result.plan.query"),)
    )
    plan = RetrievalPlan(
        route_id=plan_data["route_id"], task_id=plan_data["task_id"], route_profile=plan_data["route_profile"],
        scope=scope, history_mode=plan_data["history_mode"], queries=queries,
        candidate_budget=_mapping(plan_data["candidate_budget"], "router_result.plan.candidate_budget"),
        router_config_version=plan_data["router_config_version"], fingerprint=plan_data["fingerprint"],
    )
    candidates = tuple(
        Candidate(
            candidate_id=value["candidate_id"], source_type=value["source_type"], project_id=value.get("project_id"),
            content_type=value["content_type"], lifecycle=value["lifecycle"], source_revision=value.get("source_revision"),
            canonical_ref=_mapping(value["canonical_ref"], "router_result.candidate.canonical_ref"),
            retrieved_by=tuple(_sequence(value["retrieved_by"], "router_result.candidate.retrieved_by")),
            match_signals=tuple(_sequence(value["match_signals"], "router_result.candidate.match_signals")),
            retrieval_score=value["retrieval_score"],
        )
        for value in _sequence(document.get("candidates", []), "router_result.candidates")
        for value in (_mapping(value, "router_result.candidate"),)
    )
    return RouterResult(
        status=document["status"], plan=plan,
        input_revisions=_mapping(document.get("input_revisions"), "router_result.input_revisions"),
        candidates=candidates,
        degraded_reasons=tuple(_sequence(document.get("degraded_reasons", []), "router_result.degraded_reasons")),
        error=document.get("error"),
        telemetry=_mapping(document.get("telemetry", {}), "router_result.telemetry"),
    )
