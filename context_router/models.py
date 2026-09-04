"""Stable, privacy-safe contracts for Phase 17 routing."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Optional


ROUTER_SCHEMA_VERSION = 1
ROUTE_STATUSES = frozenset(
    {"SUCCESS", "DEGRADED", "EMPTY", "STALE_INPUT", "INVALID_TASK", "SCOPE_ERROR", "FAILED"}
)
ROUTER_MODES = frozenset({"OFF", "SHADOW"})
SCOPE_MODES = frozenset({"CURRENT_PROJECT", "GLOBAL_ONLY", "SELECTED_PROJECTS"})
HISTORY_MODES = frozenset({"ACTIVE_ONLY", "ACTIVE_PLUS_RELEVANT_HISTORY", "HISTORY_ONLY"})


class RouterContractError(ValueError):
    """Raised when a caller supplies an incoherent routing contract."""


def _string(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RouterContractError(f"{name} must be a non-empty string")
    return value.strip()


def _unique_strings(values: tuple[str, ...] | list[str], name: str) -> tuple[str, ...]:
    if not isinstance(values, (tuple, list)):
        raise RouterContractError(f"{name} must be a sequence")
    normalized = tuple(_string(value, name) for value in values)
    if len(normalized) != len(set(normalized)):
        raise RouterContractError(f"{name} must not contain duplicate values")
    return tuple(sorted(normalized))


@dataclass(frozen=True)
class RoutingOptions:
    """Trusted caller policy. Raw task text never creates these permissions."""

    scope_mode: str = "CURRENT_PROJECT"
    selected_project_ids: tuple[str, ...] = ()
    include_global: bool = True
    history_mode: str = "ACTIVE_ONLY"
    allow_archived_history: bool = False
    mode: str = "SHADOW"

    def __post_init__(self) -> None:
        if self.scope_mode not in SCOPE_MODES:
            raise RouterContractError(f"Unsupported scope_mode: {self.scope_mode}")
        if self.history_mode not in HISTORY_MODES:
            raise RouterContractError(f"Unsupported history_mode: {self.history_mode}")
        if self.mode not in ROUTER_MODES:
            raise RouterContractError(f"Unsupported router mode: {self.mode}")
        if not isinstance(self.include_global, bool):
            raise RouterContractError("include_global must be boolean")
        if not isinstance(self.allow_archived_history, bool):
            raise RouterContractError("allow_archived_history must be boolean")
        selected = _unique_strings(self.selected_project_ids, "selected_project_ids")
        if self.scope_mode == "SELECTED_PROJECTS" and not selected:
            raise RouterContractError("SELECTED_PROJECTS requires selected_project_ids")
        if self.scope_mode != "SELECTED_PROJECTS" and selected:
            raise RouterContractError("selected_project_ids are allowed only for SELECTED_PROJECTS")
        object.__setattr__(self, "selected_project_ids", selected)

    def to_dict(self) -> dict[str, Any]:
        return {
            "scope_mode": self.scope_mode,
            "selected_project_ids": list(self.selected_project_ids),
            "include_global": self.include_global,
            "history_mode": self.history_mode,
            "allow_archived_history": self.allow_archived_history,
            "mode": self.mode,
        }


@dataclass(frozen=True)
class RouteScope:
    """The finite scope available to one route invocation."""

    mode: str
    project_ids: tuple[str, ...]
    include_global: bool

    def __post_init__(self) -> None:
        if self.mode not in SCOPE_MODES:
            raise RouterContractError(f"Unsupported route scope: {self.mode}")
        object.__setattr__(self, "project_ids", _unique_strings(self.project_ids, "project_ids"))
        if self.mode == "CURRENT_PROJECT" and len(self.project_ids) != 1:
            raise RouterContractError("CURRENT_PROJECT requires exactly one project")
        if self.mode == "GLOBAL_ONLY" and self.project_ids:
            raise RouterContractError("GLOBAL_ONLY cannot include projects")
        if self.mode == "SELECTED_PROJECTS" and not self.project_ids:
            raise RouterContractError("SELECTED_PROJECTS requires projects")

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "project_ids": list(self.project_ids),
            "include_global": self.include_global,
        }


@dataclass(frozen=True)
class RetrievalQuery:
    query_id: str
    source: str
    strategy: str
    terms: tuple[str, ...] = ()
    memory_types: tuple[str, ...] = ()
    pass_name: str = "strict"

    def __post_init__(self) -> None:
        _string(self.query_id, "query_id")
        _string(self.source, "query.source")
        _string(self.strategy, "query.strategy")
        if self.pass_name not in {"strict", "fallback"}:
            raise RouterContractError("query.pass_name must be strict or fallback")
        object.__setattr__(self, "terms", _unique_strings(self.terms, "query.terms"))
        object.__setattr__(self, "memory_types", _unique_strings(self.memory_types, "query.memory_types"))

    def to_dict(self) -> dict[str, Any]:
        return {
            "query_id": self.query_id,
            "source": self.source,
            "strategy": self.strategy,
            "terms": list(self.terms),
            "memory_types": list(self.memory_types),
            "pass": self.pass_name,
        }


@dataclass(frozen=True)
class RetrievalPlan:
    route_id: str
    task_id: str
    route_profile: str
    scope: RouteScope
    history_mode: str
    queries: tuple[RetrievalQuery, ...]
    candidate_budget: Mapping[str, int]
    router_config_version: int
    fingerprint: str

    def __post_init__(self) -> None:
        _string(self.route_id, "route_id")
        _string(self.task_id, "task_id")
        _string(self.route_profile, "route_profile")
        if self.history_mode not in HISTORY_MODES:
            raise RouterContractError(f"Unsupported history mode: {self.history_mode}")
        if len({query.query_id for query in self.queries}) != len(self.queries):
            raise RouterContractError("RetrievalPlan queries must have unique IDs")
        for source, budget in self.candidate_budget.items():
            _string(source, "candidate budget source")
            if isinstance(budget, bool) or not isinstance(budget, int) or budget < 0:
                raise RouterContractError("candidate budgets must be non-negative integers")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": ROUTER_SCHEMA_VERSION,
            "route_id": self.route_id,
            "task_id": self.task_id,
            "route_profile": self.route_profile,
            "scope": self.scope.to_dict(),
            "history_mode": self.history_mode,
            "queries": [query.to_dict() for query in self.queries],
            "candidate_budget": dict(sorted(self.candidate_budget.items())),
            "router_config_version": self.router_config_version,
            "fingerprint": self.fingerprint,
        }


@dataclass(frozen=True)
class Candidate:
    """A content-free, canonical reference with retrieval provenance."""

    candidate_id: str
    source_type: str
    project_id: Optional[str]
    content_type: str
    lifecycle: str
    source_revision: Optional[int]
    canonical_ref: Mapping[str, Any]
    retrieved_by: tuple[str, ...]
    match_signals: tuple[str, ...]
    retrieval_score: float

    def __post_init__(self) -> None:
        _string(self.candidate_id, "candidate_id")
        _string(self.source_type, "source_type")
        _string(self.content_type, "content_type")
        _string(self.lifecycle, "lifecycle")
        if self.project_id is not None:
            _string(self.project_id, "candidate.project_id")
        if self.source_revision is not None and (
            isinstance(self.source_revision, bool)
            or not isinstance(self.source_revision, int)
            or self.source_revision < 0
        ):
            raise RouterContractError("candidate.source_revision must be a non-negative integer")
        if not isinstance(self.canonical_ref, Mapping) or not self.canonical_ref:
            raise RouterContractError("candidate.canonical_ref must be a non-empty mapping")
        object.__setattr__(self, "retrieved_by", _unique_strings(self.retrieved_by, "candidate.retrieved_by"))
        object.__setattr__(self, "match_signals", _unique_strings(self.match_signals, "candidate.match_signals"))
        if isinstance(self.retrieval_score, bool) or not isinstance(self.retrieval_score, (int, float)):
            raise RouterContractError("candidate.retrieval_score must be numeric")

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "source_type": self.source_type,
            "project_id": self.project_id,
            "content_type": self.content_type,
            "lifecycle": self.lifecycle,
            "source_revision": self.source_revision,
            "canonical_ref": dict(sorted(self.canonical_ref.items())),
            "retrieved_by": list(self.retrieved_by),
            "match_signals": list(self.match_signals),
            "retrieval_score": float(self.retrieval_score),
        }


@dataclass(frozen=True)
class RouterResult:
    status: str
    plan: Optional[RetrievalPlan]
    input_revisions: Mapping[str, Any]
    candidates: tuple[Candidate, ...] = ()
    degraded_reasons: tuple[str, ...] = ()
    error: Optional[str] = None
    telemetry: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.status not in ROUTE_STATUSES:
            raise RouterContractError(f"Unsupported route status: {self.status}")
        if not isinstance(self.input_revisions, Mapping):
            raise RouterContractError("input_revisions must be a mapping")
        ids = tuple(candidate.candidate_id for candidate in self.candidates)
        if len(ids) != len(set(ids)):
            raise RouterContractError("RouterResult candidates must be deduplicated")
        object.__setattr__(self, "degraded_reasons", _unique_strings(self.degraded_reasons, "degraded_reasons"))
        if self.error is not None:
            _string(self.error, "router error")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": ROUTER_SCHEMA_VERSION,
            "status": self.status,
            "plan": self.plan.to_dict() if self.plan else None,
            "input_revisions": dict(self.input_revisions),
            "candidates": [candidate.to_dict() for candidate in self.candidates],
            "degraded_reasons": list(self.degraded_reasons),
            "error": self.error,
            "telemetry": dict(self.telemetry),
        }
