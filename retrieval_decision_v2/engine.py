"""Deterministic, read-only PRE-08 retrieval decision engine."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import math
import re
from typing import Any, Mapping, Optional

from .models import DecisionOptions, DecisionResult, Need, NeedPlan, SelectedCandidate


POLICY_VERSION = "retrieval-decision-v2"
ACTIVE_LIFECYCLES = frozenset({"ACTIVE"})
HISTORY_LIFECYCLES = frozenset({"ACTIVE", "RESOLVED", "SUPERSEDED", "HISTORICAL"})
_QUERY_STOP = frozenset('the a an and or to for from with of in on at is are was were be been we i our it this that which what how did do does should would can use using decided decision please implement review explain continue project current previous only while scenario help me my ve veya bir bu şu için ile ne nasıl hangi kullan karar proje devam et'.split())


def _terms(text):
    return {word for word in re.findall(r'[^\W_]+', str(text).casefold()) if len(word) > 2 and not word.isdigit() and word not in _QUERY_STOP}


def _text_scores(query, texts):
    """Ephemeral inverse-frequency term evidence, never corpus labels or IDs."""
    words = _terms(query)
    documents = {key: _terms(text) for key, text in texts.items()}
    weights = {word: math.log(1 + (len(documents) + 1) / (1 + sum(word in doc for doc in documents.values()))) for word in words}
    total = sum(weights.values()) or 1
    return {key: sum(weights[word] for word in words & doc) / total for key, doc in documents.items()}, bool(words)
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


def _authority_rows(result: Any) -> tuple[Any, ...]:
    """Return authority rows without collapsing duplicate candidate IDs."""
    return tuple(_get(result, "candidates", ()) or ())


def _coverage_failure(
    *,
    policy_version: str,
    plan: NeedPlan,
    revisions: Mapping[str, Any],
    candidates_seen: int,
    eligible_count: int,
    authority_count: int,
    coverage: str,
) -> DecisionResult:
    """Build a content-free authority coverage failure result."""
    return DecisionResult(
        status="FAILED",
        policy_version=policy_version,
        input_revisions=dict(revisions),
        need_plan=plan,
        error="AUTHORITY_COVERAGE_UNAVAILABLE",
        telemetry={
            "authority_used": False,
            "authority_coverage": coverage,
            "candidates_seen": candidates_seen,
            "eligible_candidates": eligible_count,
            "authority_rows": authority_count,
        },
    )


def _revision_map(result: Any) -> Mapping[str, Any]:
    revisions = _get(result, "input_revisions", {})
    return revisions if isinstance(revisions, Mapping) else {}


def _same_revisions(left: Mapping[str, Any], right: Mapping[str, Any]) -> bool:
    return all(key in left and key in right and left[key] == right[key] for key in ('memory', 'state'))


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
    for record in (*active_blockers, *(_get(state, "constraints", ()) or ())):
        identity = _get(record, "id", None)
        if identity:
            needs.append(Need("need_record_" + str(identity), "record", "critical", domain=str(identity)))
    for text in explicit:
        needs.append(Need("need_explicit_" + hashlib.sha256(str(text).encode()).hexdigest()[:16], "task", "critical"))
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
        reference = _get(candidate, "canonical_ref", {})
        if kind == "record" and _get(reference, "item_id") == need.domain:
            matched.append(need.need_id)
        elif kind == "state" and (source == "state" or content_type in {"blocker", "work_item", "requirement", "risk", "milestone", "objective", "state"}):
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
        if isinstance(expected, Mapping):
            expected = expected.get('revision')
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
        candidate_texts: Optional[Mapping[str, str]] = None,
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
        authority_status = ""
        authority_rows: tuple[Any, ...] = ()
        if resolution_result is not None:
            authority_status = str(_get(resolution_result, "status", ""))
            if authority_status in {"STALE_INPUT", "INVALID_INPUT", "SCOPE_ERROR", "FAILED"}:
                return self._error("STALE_INPUT" if authority_status == "STALE_INPUT" else "FAILED", "AUTHORITY_INPUT_UNAVAILABLE", plan, revisions)
            authority_revisions = _revision_map(resolution_result)
            if authority_revisions and revisions and not _same_revisions(revisions, authority_revisions):
                return self._error("STALE_INPUT", "ROUTER_AUTHORITY_REVISION_MISMATCH", plan, revisions)
            authority_rows = _authority_rows(resolution_result)
        authorities: dict[str, Any] = {}

        candidates = tuple(_get(router_result, "candidates", ()) or ())
        text_scores, has_query = _text_scores(_task_field(task_state, 'raw_request', ''), candidate_texts or {})
        best_text = max(text_scores.values(), default=0)
        if options.mode == "OFF":
            return DecisionResult(status="EMPTY", policy_version=self.policy_version, input_revisions=dict(revisions), need_plan=plan, telemetry={"mode": "OFF", "selected": 0})

        omitted: dict[str, str] = {}
        eligible: list[Any] = []
        authority_rows_by_id: dict[str, list[Any]] = {}
        for row in authority_rows:
            row_id = str(_get(row, "candidate_id", ""))
            authority_rows_by_id.setdefault(row_id, []).append(row)
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
            # Preserve the existing hard authority scope filter before coverage
            # validation. A foreign-project row can never satisfy this
            # candidate, but it must not block other eligible candidates.
            rows = authority_rows_by_id.get(candidate_id, [])
            if len(rows) == 1:
                candidate_project = _get(candidate, "project_id", None)
                authority_project = _get(rows[0], "project_id", object())
                if authority_project != candidate_project:
                    omitted[candidate_id] = "AUTHORITY_SCOPE_MISMATCH"
                    continue
            eligible.append(candidate)

        eligible_ids = {str(_get(candidate, "candidate_id", "")) for candidate in eligible}
        rows_by_id = {row_id: rows for row_id, rows in authority_rows_by_id.items() if row_id in eligible_ids}

        if eligible:
            if resolution_result is None:
                coverage = "missing"
            elif authority_status == "EMPTY":
                coverage = "empty"
            elif any(len(rows) > 1 for rows in rows_by_id.values()):
                coverage = "duplicate"
            elif authority_status not in {"SUCCESS", "DEGRADED"}:
                coverage = "empty" if not authority_rows else "partial"
            else:
                coverage = "full"
                has_any_row = bool(rows_by_id)
                for candidate in eligible:
                    candidate_id = str(_get(candidate, "candidate_id", ""))
                    rows = rows_by_id.get(candidate_id, [])
                    candidate_project = _get(candidate, "project_id", None)
                    if len(rows) != 1:
                        coverage = "partial" if has_any_row else "missing"
                        break
                    authority_project = _get(rows[0], "project_id", object())
                    if authority_project != candidate_project:
                        coverage = "partial"
                        break
            if coverage != "full":
                return _coverage_failure(
                    policy_version=self.policy_version,
                    plan=plan,
                    revisions=revisions,
                    candidates_seen=len(candidates),
                    eligible_count=len(eligible),
                    authority_count=len(authority_rows),
                    coverage=coverage,
                )
            authorities = _authority_candidates(resolution_result)

        ranked: list[_Ranked] = []
        # A need matched only by a broad content-type category (any "state"
        # or "constraint"-shaped candidate) is not evidence that a specific
        # candidate is on-topic; exempting the whole category from the
        # relevance filter is what let unrelated noise flood the selection.
        # A precise per-record match (an exact tracked blocker/constraint id)
        # is trusted without a lexical check. A broad match that fails
        # relevance is parked here so a critical need never goes completely
        # uncovered, without re-admitting every same-category candidate.
        relevance_omitted: dict[str, list[_Ranked]] = {}
        for candidate in eligible:
            candidate_id = str(_get(candidate, "candidate_id", ""))
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
            matched_critical = tuple(need for need in plan.needs if need.priority == "critical" and need.need_id in needs)
            critical_bonus = 0.15 if matched_critical else 0.0
            precise_critical = any(need.kind == "record" for need in matched_critical)
            score = round(min(1.0, retrieval_score * 0.5 + need_bonus + critical_bonus), 6)
            if candidate_texts is not None and has_query:
                lexical = text_scores.get(candidate_id, 0)
                if not precise_critical and (lexical == 0 or lexical < best_text * .35):
                    omitted[candidate_id] = 'INSUFFICIENT_TASK_RELEVANCE'
                    if matched_critical:
                        item = _Ranked(candidate, needs, score, retrieval_score, _candidate_channels(candidate), ())
                        for need in matched_critical:
                            relevance_omitted.setdefault(need.need_id, []).append(item)
                    continue
                score = round(min(1.0, lexical * .85 + retrieval_score * .1 + critical_bonus), 6)
            reasons = ("AUTHORITY_UNRESOLVED",) if authority_status in {"UNRESOLVED", "CONTESTED"} else ()
            ranked.append(_Ranked(candidate, needs, score, retrieval_score, _candidate_channels(candidate), reasons))

        critical = {need.need_id for need in plan.needs if need.priority == "critical"}
        ranked.sort(key=lambda item: (not bool(critical.intersection(item.needs)), -item.score, -item.retrieval_score, _get(item.candidate, "candidate_id")))
        selected: list[SelectedCandidate] = []
        groups: set[str] = set()
        covered_critical: set[str] = set()

        def _try_select(item: _Ranked) -> bool:
            candidate = item.candidate
            candidate_id = str(_get(candidate, "candidate_id"))
            authority = authorities.get(candidate_id)
            claim = _get(authority, "claim", None)
            fingerprint = _get(claim, "dedup_fingerprint", None)
            group = str(fingerprint or candidate_id)
            if group in groups and not (critical.intersection(item.needs) - covered_critical):
                omitted[candidate_id] = "REDUNDANT_CLAIM"
                return False
            if len(selected) >= options.max_selected:
                omitted[candidate_id] = "DECISION_BUDGET"
                return False
            groups.add(group)
            covered_critical.update(critical.intersection(item.needs))
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
            return True

        for item in ranked:
            _try_select(item)

        # Guarantee coverage, never a category: a critical need still with no
        # coverage gets exactly one best-effort candidate back, not every
        # same-category candidate that lost the relevance filter.
        for need_id in sorted(critical - covered_critical):
            pool = relevance_omitted.get(need_id, [])
            if not pool:
                continue
            pool.sort(key=lambda item: (-item.score, -item.retrieval_score, _get(item.candidate, "candidate_id")))
            best = pool[0]
            best_id = str(_get(best.candidate, "candidate_id"))
            if omitted.get(best_id) == 'INSUFFICIENT_TASK_RELEVANCE':
                del omitted[best_id]
            backfilled = _Ranked(best.candidate, best.needs, best.score, best.retrieval_score, best.channels, best.reasons + ("CRITICAL_BACKFILL",))
            if not _try_select(backfilled):
                omitted[best_id] = 'INSUFFICIENT_TASK_RELEVANCE'

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
                "authority_used": bool(eligible),
                "authority_coverage": "full" if eligible else "empty",
            },
        )
