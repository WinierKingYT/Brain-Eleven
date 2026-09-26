"""Strict JSON decoding for content-safe Authority CLI/cache contracts."""

from __future__ import annotations

import re
from datetime import datetime
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


_STATE_STATUSES = frozenset({
    "AVAILABLE", "PROJECT_UNKNOWN", "PROJECT_ARCHIVED", "STATE_NOT_FOUND",
    "STATE_CORRUPT", "STATE_UNAVAILABLE",
})
_ERROR_STATE_STATUSES = frozenset({
    "PROJECT_UNKNOWN", "STATE_NOT_FOUND", "STATE_CORRUPT", "STATE_UNAVAILABLE",
})
_SOURCE_TYPES = frozenset({"user", "system", "tool"})
_SEVERITIES = frozenset({"LOW", "MEDIUM", "HIGH", "CRITICAL"})
_SENSITIVE_PATTERNS = (
    re.compile(r"\b(?:api[_ -]?key|password|secret|token)\s*[:=]\s*\S+", re.IGNORECASE),
    re.compile(r"\b(?:sk|ghp|xox[baprs])_[A-Za-z0-9_-]{12,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
)


def _exact_fields(
    value: Mapping[str, Any],
    field: str,
    required: set[str],
    optional: set[str] | frozenset[str] = frozenset(),
) -> None:
    fields = set(value)
    if not required <= fields or fields - required - optional:
        raise ValueError(f"{field} has invalid fields")


def _nonempty_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value


def _string(value: Any, field: str, *, prefix: str | None = None) -> str:
    value = _nonempty_string(value, field)
    if prefix is not None and not value.strip().startswith(prefix):
        raise ValueError(f"{field} has an invalid namespace")
    if any(pattern.search(value) for pattern in _SENSITIVE_PATTERNS):
        raise ValueError(f"{field} contains prohibited sensitive data")
    return value


def _timestamp(value: Any, field: str) -> str:
    value = _string(value, field)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ValueError(f"{field} must be a timezone-aware ISO-8601 timestamp") from None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field} must be a timezone-aware ISO-8601 timestamp")
    return value


def _nonnegative_integer(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field} must be a non-negative integer")
    return value


def _source(value: Any, field: str) -> Mapping[str, Any]:
    value = _mapping(value, field)
    _exact_fields(value, field, {"type"}, {"reference"})
    source_type = _string(value["type"], f"{field}.type")
    if source_type not in _SOURCE_TYPES:
        raise ValueError(f"{field}.type is unsupported")
    reference = value.get("reference")
    if reference is not None:
        _string(reference, f"{field}.reference")
    return value


def _record(
    value: Any,
    field: str,
    *,
    prefix: str,
    statuses: frozenset[str],
    text_field: str = "text",
    extra_required: set[str] | frozenset[str] = frozenset(),
    extra_optional: set[str] | frozenset[str] = frozenset(),
) -> Mapping[str, Any]:
    value = _mapping(value, field)
    required = {"id", text_field, "status", "source", "created_at", "updated_at"} | extra_required
    _exact_fields(value, field, required, extra_optional)
    _string(value["id"], f"{field}.id", prefix=prefix)
    _string(value[text_field], f"{field}.{text_field}")
    status = _nonempty_string(value["status"], f"{field}.status")
    if status not in statuses:
        raise ValueError(f"{field}.status is unsupported")
    _source(value["source"], f"{field}.source")
    _timestamp(value["created_at"], f"{field}.created_at")
    _timestamp(value["updated_at"], f"{field}.updated_at")
    if "phase_id" in extra_required:
        _string(value["phase_id"], f"{field}.phase_id")
    if "severity" in extra_required:
        severity = _string(value["severity"], f"{field}.severity")
        if severity not in _SEVERITIES:
            raise ValueError(f"{field}.severity is unsupported")
    if value.get("memory_ref") is not None:
        _string(value["memory_ref"], f"{field}.memory_ref", prefix="mem_")
    return value


def _records(value: Any, field: str, parser) -> tuple[Mapping[str, Any], ...]:
    values = _sequence(value, field)
    records = tuple(parser(item, f"{field}[{index}]") for index, item in enumerate(values))
    if len({record["id"] for record in records}) != len(records):
        raise ValueError(f"{field} contains duplicate IDs")
    return records


def _memory_ids(value: Any, field: str) -> list[str]:
    values = _sequence(value, field)
    for index, item in enumerate(values):
        _string(item, f"{field}[{index}]", prefix="mem_")
    if len(set(values)) != len(values):
        raise ValueError(f"{field} contains duplicate IDs")
    return values


def _references(value: Any, field: str) -> Mapping[str, Any]:
    value = _mapping(value, field)
    _exact_fields(value, field, {"status", "valid", "dangling", "wrong_project"}, {"error"})
    status = _string(value["status"], f"{field}.status")
    if status not in {"not_checked", "checked", "unavailable"}:
        raise ValueError(f"{field}.status is unsupported")
    arrays = [_memory_ids(value[name], f"{field}.{name}") for name in ("valid", "dangling", "wrong_project")]
    if status == "not_checked" and any(arrays):
        raise ValueError(f"{field} is inconsistent with not_checked status")
    if status != "unavailable" and "error" in value:
        raise ValueError(f"{field}.error is not allowed for this status")
    if "error" in value:
        _nonempty_string(value["error"], f"{field}.error")
    return value


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
    from brain_eleven.state.resolver import CurrentProjectState
    from scripts.task_model import TaskEnvelope
    from brain_eleven.runtime.task_state_context import (
        TASK_STATE_CONTEXT_SCHEMA_VERSION,
        TaskStateContext,
        TaskStateLineage,
    )

    document = _mapping(document, "task_state")
    if document.get("schema_version") != TASK_STATE_CONTEXT_SCHEMA_VERSION:
        raise ValueError("task_state schema_version is unsupported")
    if "lineage" not in document:
        raise ValueError("task_state.lineage is required")
    if set(document) != {"schema_version", "task", "state", "lineage"}:
        raise ValueError("task_state fields are invalid")
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
    if project_id is not None:
        _nonempty_string(project_id, "task_state.state.project_id")
    status = _nonempty_string(state_data["status"], "task_state.state.status")
    if status not in _STATE_STATUSES:
        raise ValueError("task_state.state.status is unsupported")
    revision = state_data["state_revision"]
    if revision is not None:
        _nonnegative_integer(revision, "task_state.state.state_revision")
    updated_at = state_data["updated_at"]
    if updated_at is not None:
        _timestamp(updated_at, "task_state.state.updated_at")
    error = state_data["error"]
    if error is not None:
        _nonempty_string(error, "task_state.state.error")
    archived = state_data["archived"]
    if not isinstance(archived, bool):
        raise ValueError("task_state.state.archived must be a boolean")

    freshness = _mapping(state_data["freshness"], "task_state.state.freshness")
    _exact_fields(freshness, "task_state.state.freshness", {"status", "age_days"})
    freshness_status = _nonempty_string(freshness["status"], "task_state.state.freshness.status")
    if freshness_status not in {"current", "stale_candidate", "unknown"}:
        raise ValueError("task_state.state.freshness.status is unsupported")
    age_days = freshness["age_days"]
    if freshness_status == "unknown":
        if age_days is not None:
            raise ValueError("task_state.state.freshness.age_days must be null when status is unknown")
    elif age_days is None:
        raise ValueError("task_state.state.freshness.age_days is required for current state")
    else:
        _nonnegative_integer(age_days, "task_state.state.freshness.age_days")

    current = _mapping(state_data["current"], "task_state.state.current")
    _exact_fields(current, "task_state.state.current", {"phase_id", "milestone", "objective"})
    if current["phase_id"] is not None:
        _string(current["phase_id"], "task_state.state.current.phase_id")
    milestone = current["milestone"]
    if milestone is not None:
        _record(
            milestone, "task_state.state.current.milestone", prefix="mil_",
            statuses=frozenset({"PLANNED", "ACTIVE", "BLOCKED", "COMPLETED", "CANCELLED"}),
            text_field="title", extra_required={"phase_id"},
        )
    objective = current["objective"]
    if objective is not None:
        _record(objective, "task_state.state.current.objective", prefix="obj_", statuses=frozenset({"ACTIVE"}))

    requirements = _records(
        state_data["active_requirements"], "task_state.state.active_requirements",
        lambda value, field: _record(value, field, prefix="req_", statuses=frozenset({"ACTIVE"})),
    )
    work_items = _records(
        state_data["active_work_items"], "task_state.state.active_work_items",
        lambda value, field: _record(value, field, prefix="wrk_", statuses=frozenset({"TODO", "ACTIVE", "BLOCKED"})),
    )
    blockers = _records(
        state_data["active_blockers"], "task_state.state.active_blockers",
        lambda value, field: _record(
            value, field, prefix="blk_", statuses=frozenset({"ACTIVE"}),
            extra_required={"severity"}, extra_optional={"memory_ref"},
        ),
    )
    constraints = _records(
        state_data["constraints"], "task_state.state.constraints",
        lambda value, field: _record(value, field, prefix="con_", statuses=frozenset({"ACTIVE"})),
    )
    risks = _records(
        state_data["risks"], "task_state.state.risks",
        lambda value, field: _record(
            value, field, prefix="rsk_", statuses=frozenset({"ACTIVE"}), extra_required={"severity"},
        ),
    )
    references = _references(state_data["references"], "task_state.state.references")

    empty_projection = (
        revision is None and updated_at is None
        and freshness == {"status": "unknown", "age_days": None}
        and current == {"phase_id": None, "milestone": None, "objective": None}
        and not requirements and not work_items and not blockers and not constraints and not risks
        and references.get("status") == "not_checked"
    )
    if status in _ERROR_STATE_STATUSES:
        if not empty_projection:
            raise ValueError("task_state.state must use the empty error projection")
        if error is None:
            raise ValueError("task_state.state.error is required for error status")
        if status in {"PROJECT_UNKNOWN", "STATE_NOT_FOUND"} and archived:
            raise ValueError("task_state.state.archived is inconsistent with error status")
    elif status == "AVAILABLE":
        if archived:
            raise ValueError("task_state.state.archived is inconsistent with AVAILABLE status")
        if revision is None or updated_at is None or freshness_status == "unknown":
            raise ValueError("task_state.state is incomplete for AVAILABLE status")
        if error is not None:
            raise ValueError("task_state.state.error is not allowed for AVAILABLE status")
    else:
        if not archived:
            raise ValueError("task_state.state.archived is inconsistent with PROJECT_ARCHIVED status")
        if empty_projection:
            if error is None:
                raise ValueError("task_state.state.error is required for empty PROJECT_ARCHIVED status")
        elif revision is None or updated_at is None or freshness_status == "unknown" or error is not None:
            raise ValueError("task_state.state is inconsistent with populated PROJECT_ARCHIVED status")

    lineage = TaskStateLineage.from_dict(document.get("lineage"))
    task_project_id = task.project.project_id
    if lineage.status == "resolved":
        if lineage.project_id != task_project_id or lineage.project_id != project_id:
            raise ValueError("task_state lineage project identity does not match task/state")
    elif task_project_id is not None or project_id is not None:
        raise ValueError("task_state non-resolved lineage must not carry project identity")

    return TaskStateContext(
        task=task,
        state=CurrentProjectState(
            project_id=project_id,
            status=status,
            state_revision=revision,
            updated_at=updated_at,
            freshness=freshness,
            current=current,
            active_requirements=requirements,
            active_work_items=work_items,
            active_blockers=blockers,
            constraints=constraints,
            risks=risks,
            references=references,
            error=error,
            archived=archived,
        ),
        lineage=lineage,
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
