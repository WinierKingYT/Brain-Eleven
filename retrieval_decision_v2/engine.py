"""Deterministic, read-only PRE-08 retrieval decision engine."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Optional

from .models import DecisionOptions, DecisionResult, Need, NeedPlan, SelectedCandidate


POLICY_VERSION = "retrieval-decision-v2"
ACTIVE_LIFECYCLES = frozenset({"ACTIVE"})
HISTORY_LIFECYCLES = frozenset({"ACTIVE", "RESOLVED", "SUPERSEDED", "HISTORICAL"})
HARD_AUTHORITY_REJECTIONS = frozenset({"SUPERSEDED", "HISTORICAL", "INAPPLICABLE", "INVALID"})


def _get(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, Mapping):
        return value.get(name, default)
    return getattr(value, name, default)


def _task_field(task_state: Any, name: str, default: Any = None) -> Any:
    task = _get(task_state, "task", None)
    return _get(task, name, default)


def _project_id(task_state: Any) -> Optional[str]:
    project = _task_field(task_state, "project", None)
    return _get(project, "project_id", None)


def _scope(plan: Any) -> Any:
    return _get(plan, "scope", {})


def _scope_value(scope: Any, name: str, default: Any = None) -> Any:
    return _get(scope, name, default)


def _authority_candidates(result: Any) -> dict[str, Any]:
    return {str(_get(item, "candidate_id")): item for item in (_get(result, "candidates", ()) or ())}


def _revision_map(result: Any) -> Mapping[str, Any]:
    revisions = _get(result, "input_revisions", {})
    return revisions if isinstance(revisions, Mapping) else {}


def _same_revisions(left: Mapping[str, Any], right: Mapping[str, Any]) -> bool:
    return dict(left) == dict(right)


def build_need_plan(task_state: Any) -> NeedPlan:
    """Build coarse needs from explicit task/state fields without LLM calls."""
    intent = str(_get(_task_field(task_state, "intent", None), "value", "UNKNOWN")).upper()
    context_needs = {str(item).casefold() for item in (_task_field(task_state, "context_needs", ()) or ())}
    explicit = tuple(_task_field(task_state, "explicit_constraints", ()) or ())
    inherited = tuple(_task_field(task_state, "inherited_constraints", ()) or ())
    state = _get(task_state, "state", None)
    active_blockers = _get(state, "active_blockers", ()) or ()
    needs: list[Need] = []

    if intent in {"IMPLEMENT", "DEBUG", "REVIEW", "DESIGN", "PLAN", "MIGRATE", "TEST"} or "project_decisions" in context_needs:
        needs.append(Need("need_decisions", "decision", "high"))
    if explicit or inherited or "constraints" in context_needs:
        needs.append(Need("need_constraints", "constraint", "critical"))
    if active_blockers or "active_blockers" in context_needs:
        needs.append(Need("need_state", "state", "critical"))
    if intent in {"DEBUG", "RESEARCH", "REVIEW"} or "previous_lessons" in context_needs:
        needs.append(Need("need_lessons", "lesson", "normal"))
    if not needs:
        needs.append(Need("need_general", "general", "normal"))
    return NeedPlan(tuple(sorted(needs, key=lambda item: (item.priority, item.need_id))))


def _need_matches(candidate: Any, plan: NeedPlan) -> tuple[str, ...]:
    source = str(_get(candidate, "source_type", "")).casefold()
    content_type = str(_get(candidate, "content_type", "")).casefold()
    signals = {str(item).casefold() for item in (_get(candidate, "match_signals", ()) or ())}
    matched: list[str] = []
    for need in plan.needs:
        kind = need.kind.casefold()
        if kind == "state" and (source == "state" or content_type in {"blocker", "work_item", "requirement", "risk", "milestone", "objective", "state"}):
            matched.append(need.need_id)
        elif kind == "decision" and (content_type in {"decision", "preference", "observation", "open_loop"} or "decision" in signals):
            matched.append(need.need_id)
        elif kind == "constraint" and (content_type in {"constraint", "requirement", "risk"} or "constraint" in signals):
            matched.append(need.need_id)
        elif kind == "lesson" and content_type == "lesson":
            matched.append(need.need_id)
        elif kind == "general":
            matched.append(need.need_id)
    return tuple(sorted(set(matched)))


def _candidate_channels(candidate: Any) -> tuple[str, ...]:
    channels = tuple(str(item) for item in (_get(candidate, "retrieved_by", ()) or ()))
    return tuple(sorted(set(channels or ("router",))))


def _allowed_by_scope(candidate: Any, scope: Any, current_project: Optional[str]) -> bool:
    candidate_project = _get(candidate, "project_id", None)
    mode = _scope_value(scope, "mode", None)
    project_ids = tuple(_scope_value(scope, "project_ids", ()) or ())
    include_global = bool(_scope_value(scope, "include_global", False))
    if candidate_project is None:
        return include_global
    if mode == "CURRENT_PROJECT":
        return current_project is not None and candidate_project == current_project and candidate_project in project_ids
    if mode == "SELECTED_PROJECTS":
        return candidate_project in project_ids
    return False


def _state_revision_matches(candidate: Any, revisions: Mapping[str, Any]) -> bool:
    source = str(_get(candidate, "source_type", "")).casefold()
    source_revision = _get(candidate, "source_revision", None)
    if source_revision is None:
        return True
    expected = revisions.get("state" if source == "state" else "memory")
    if isinstance(expected, Mapping):
        project = _get(candidate, "project_id", None)
        expected = expected.get(project)
    return expected is None or source_revision == expected


@dataclass(frozen=True)
class _Ranked:
    candidate: Any
    needs: tuple[str, ...]
    score: float
    retrieval_score: float
    channels: tuple[str, ...]
    reasons: tuple[str, ...]


class RetrievalDecisionEngine:
    """Select useful candidates after hard policy and authority filtering."""

    def __init__(self, policy_version: str = POLICY_VERSION):
        self.policy_version = policy_version

    def _error(self, status: str, reason: str, plan: NeedPlan, revisions: Mapping[str, Any] = ()) -> DecisionResult:
        return DecisionResult(status=status, policy_version=self.policy_version, input_revisions=dict(revisions), need_plan=plan, error=reason)

    def select(
        self,
        task_state: Any,
        router_result: Any,
        resolution_result: Any = None,
        *,
        options: Optional[DecisionOptions] = None,
    ) -> DecisionResult:
        """Return content-free selected references; no canonical writes occur."""
        options = options or DecisionOptions()
        plan = build_need_plan(task_state)
        router_status = str(_get(router_result, "status", ""))
        if router_status in {"INVALID_TASK", "FAILED"}:
            return self._error("FAILED", "ROUTER_INPUT_UNAVAILABLE", plan)
        if router_status == "SCOPE_ERROR":
            return self._error("SCOPE_ERROR", "ROUTER_SCOPE_ERROR", plan)
        if router_status == "STALE_INPUT":
            return self._error("STALE_INPUT", "ROUTER_INPUT_STALE", plan, _revision_map(router_result))
        route_plan = _get(router_result, "plan", None)
        if route_plan is None:
            return self._error("FAILED", "ROUTER_PLAN_REQUIRED", plan)
        scope = _scope(route_plan)
        current_project = _project_id(task_state)
        mode = _scope_value(scope, "mode", None)
        project_ids = tuple(_scope_value(scope, "project_ids", ()) or ())
        if mode not in {"CURRENT_PROJECT", "GLOBAL_ONLY", "SELECTED_PROJECTS"}:
            return self._error("SCOPE_ERROR", "INVALID_ROUTER_SCOPE", plan)
        if mode == "CURRENT_PROJECT" and (not current_project or project_ids != (current_project,)):
            return self._error("SCOPE_ERROR", "TASK_ROUTER_PROJECT_MISMATCH", plan)
        if mode == "SELECTED_PROJECTS" and not project_ids:
            return self._error("SCOPE_ERROR", "EMPTY_SELECTED_PROJECT_SCOPE", plan)

        revisions = _revision_map(router_result)
        if resolution_result is not None:
            authority_status = str(_get(resolution_result, "status", ""))
            if authority_status in {"STALE_INPUT", "INVALID_INPUT", "SCOPE_ERROR", "FAILED"}:
                return self._error("STALE_INPUT" if authority_status == "STALE_INPUT" else "FAILED", "AUTHORITY_INPUT_UNAVAILABLE", plan, revisions)
            authority_revisions = _revision_map(resolution_result)
            if authority_revisions and revisions and not _same_revisions(revisions, authority_revisions):
                return self._error("STALE_INPUT", "ROUTER_AUTHORITY_REVISION_MISMATCH", plan, revisions)
            authorities = _authority_candidates(resolution_result)
        else:
            authorities = {}

        candidates = tuple(_get(router_result, "candidates", ()) or ())
        if options.mode == "OFF":
            return DecisionResult(status="EMPTY", policy_version=self.policy_version, input_revisions=dict(revisions), need_plan=plan, telemetry={"mode": "OFF", "selected": 0})

        omitted: dict[str, str] = {}
        ranked: list[_Ranked] = []
        seen: set[str] = set()
        for candidate in candidates:
            candidate_id = str(_get(candidate, "candidate_id", ""))
            if not candidate_id or candidate_id in seen:
                if candidate_id:
                    omitted[candidate_id] = "DUPLICATE_CANDIDATE"
                continue
            seen.add(candidate_id)
            if not _allowed_by_scope(candidate, scope, current_project):
                omitted[candidate_id] = "SCOPE_FILTERED"
                continue
            lifecycle = str(_get(candidate, "lifecycle", "ACTIVE")).upper()
            if lifecycle not in (HISTORY_LIFECYCLES if options.allow_history else ACTIVE_LIFECYCLES):
                omitted[candidate_id] = "LIFECYCLE_FILTERED"
                continue
            if not _state_revision_matches(candidate, revisions):
                omitted[candidate_id] = "STALE_CANDIDATE"
                continue
            authority = authorities.get(candidate_id)
            authority_status = str(_get(authority, "status", "")).upper() if authority else ""
            if authority_status in HARD_AUTHORITY_REJECTIONS:
                omitted[candidate_id] = "AUTHORITY_FILTERED"
                continue
            candidate_project = _get(candidate, "project_id", None)
            if authority is not None and _get(authority, "project_id", candidate_project) != candidate_project:
                omitted[candidate_id] = "AUTHORITY_SCOPE_MISMATCH"
                continue
            needs = _need_matches(candidate, plan)
            retrieval_score = float(_get(candidate, "retrieval_score", 0.0) or 0.0)
            retrieval_score = max(0.0, min(1.0, retrieval_score))
            need_bonus = 0.35 if needs else 0.0
            critical_bonus = 0.15 if any(need.priority == "critical" and need.need_id in needs for need in plan.needs) else 0.0
            score = round(min(1.0, retrieval_score * 0.5 + need_bonus + critical_bonus), 6)
            reasons = ("AUTHORITY_UNRESOLVED",) if authority_status in {"UNRESOLVED", "CONTESTED"} else ()
            ranked.append(_Ranked(candidate, needs, score, retrieval_score, _candidate_channels(candidate), reasons))

        ranked.sort(key=lambda item: (-item.score, -item.retrieval_score, item.candidate.candidate_id))
        selected: list[SelectedCandidate] = []
        groups: set[str] = set()
        for item in ranked:
            candidate = item.candidate
            candidate_id = str(_get(candidate, "candidate_id"))
            authority = authorities.get(candidate_id)
            claim = _get(authority, "claim", None)
            fingerprint = _get(claim, "dedup_fingerprint", None)
            group = str(fingerprint or candidate_id)
            if group in groups:
                omitted[candidate_id] = "REDUNDANT_CLAIM"
                continue
            if len(selected) >= options.max_selected:
                omitted[candidate_id] = "DECISION_BUDGET"
                continue
            groups.add(group)
            selected.append(
                SelectedCandidate(
                    candidate_id=candidate_id,
                    source_type=str(_get(candidate, "source_type", "unknown")),
                    project_id=_get(candidate, "project_id", None),
                    content_type=str(_get(candidate, "content_type", "unknown")),
                    lifecycle=str(_get(candidate, "lifecycle", "ACTIVE")),
                    canonical_ref=dict(_get(candidate, "canonical_ref", {})),
                    needs=item.needs,
                    channels=item.channels,
                    decision_score=item.score,
                    retrieval_score=item.retrieval_score,
                    reason_codes=item.reasons,
                )
            )

        degraded = []
        if str(_get(router_result, "status", "")) == "DEGRADED":
            degraded.append("ROUTER_DEGRADED")
        if resolution_result is not None and str(_get(resolution_result, "status", "")) == "DEGRADED":
            degraded.append("AUTHORITY_DEGRADED")
        if any(reason == "STALE_CANDIDATE" for reason in omitted.values()):
            degraded.append("STALE_CANDIDATE_OMITTED")
        status = "EMPTY" if not selected else ("DEGRADED" if degraded else "SUCCESS")
        return DecisionResult(
            status=status,
            policy_version=self.policy_version,
            input_revisions=dict(revisions),
            need_plan=plan,
            selected=tuple(selected),
            omitted=omitted,
            degraded_reasons=tuple(sorted(set(degraded))),
            telemetry={
                "mode": options.mode,
                "candidates_seen": len(candidates),
                "selected": len(selected),
                "omitted": len(omitted),
                "authority_used": resolution_result is not None,
            },
        )
