"""Deterministic role, tier and redundancy classification without utility scores."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Optional

from .adapters import RehydratedCandidate
from .models import UtilityProfile
from .profile_policy import MANDATORY_ROLES
from .tokenizer import TokenEstimator


PROFILES = frozenset({"continuation", "implementation", "debugging", "architecture", "review", "research", "general"})


@dataclass(frozen=True)
class CandidateDraft:
    evidence: RehydratedCandidate
    role: str
    tier: int
    mandatory: bool
    task_fit: str
    redundancy_group: Optional[str]
    rendered_text: str
    utility: UtilityProfile


def profile_from_input(task_state: Any, resolution_result: Any, requested: Optional[str]) -> str:
    route_profile = None
    route = resolution_result.telemetry.get("route_profile") if isinstance(resolution_result.telemetry, Mapping) else None
    if isinstance(route, str):
        route_profile = route
    plan = getattr(resolution_result, "plan", None)
    if plan is not None and isinstance(getattr(plan, "route_profile", None), str):
        route_profile = plan.route_profile
    # ResolutionResult normally has no plan.  Compiler callers can use the
    # Phase 16 intent only as a bounded, deterministic fallback.
    raw_intent = str(getattr(task_state.task.intent, "value", "general")).upper()
    fallback = {
        "IMPLEMENT": "implementation",
        "DEBUG": "debugging",
        "DESIGN": "architecture",
        "REVIEW": "review",
        "RESEARCH": "research",
        "PLAN": "architecture",
    }.get(raw_intent, "general")
    if fallback not in PROFILES:
        fallback = "general"
    profile = route_profile if route_profile in PROFILES else fallback
    if requested is not None and requested != profile:
        raise ValueError("Compiler profile must match the upstream task/router profile")
    return profile


def _memory_role(record: Mapping[str, Any]) -> str:
    memory_type = str(record.get("type", "")).casefold()
    return {
        "decision": "DECISION",
        "preference": "PREFERENCE",
        "lesson": "LESSON",
        "open_loop": "OPEN_LOOP",
        "requirement": "REQUIREMENT",
        "constraint": "CONSTRAINT",
        "fact": "IMPLEMENTATION_FACT",
    }.get(memory_type, "SUPPORTING_EVIDENCE")


def role_for(item: RehydratedCandidate) -> str:
    status = item.resolution.status
    if status == "IMPLEMENTATION_GAP":
        return "IMPLEMENTATION_GAP"
    if status in {"CONTESTED", "UNRESOLVED"}:
        return "CONFLICT"
    if status == "HISTORICAL":
        return "HISTORICAL_CONTEXT"
    if item.state_kind is not None:
        return {
            "objective": "CURRENT_STATE",
            "milestone": "CURRENT_STATE",
            "requirement": "REQUIREMENT",
            "constraint": "CONSTRAINT",
            "blocker": "IMPLEMENTATION_GAP",
            "risk": "CONSTRAINT",
            "work_item": "CURRENT_STATE",
        }.get(item.state_kind, "CURRENT_STATE")
    return _memory_role(item.record)


def tier_for(
    role: str, status: str, profile: str, mandatory_roles: frozenset[str] = frozenset(MANDATORY_ROLES)
) -> tuple[int, bool, str]:
    if role in mandatory_roles:
        return 0, True, "exact"
    if role == "CURRENT_STATE":
        return 1, False, "direct"
    if role == "DECISION":
        return 1 if profile in {"implementation", "architecture", "review", "continuation"} else 2, False, "direct"
    if role in {"IMPLEMENTATION_FACT", "LESSON"}:
        return 2 if profile in {"implementation", "debugging", "review"} else 3, False, "related"
    if role == "PREFERENCE":
        return 3, False, "related"
    if role == "OPEN_LOOP":
        return 3 if profile in {"continuation", "debugging"} else 4, False, "related"
    if role == "HISTORICAL_CONTEXT" or status == "HISTORICAL":
        return 4, False, "historical"
    return 3, False, "related"


def redundancy_groups(items: Iterable[RehydratedCandidate]) -> Mapping[str, str]:
    """Only canonical dedup fingerprints form groups; prose is never compared."""
    groups: dict[tuple[Optional[str], str], list[str]] = {}
    for item in items:
        fingerprint = item.resolution.claim.dedup_fingerprint
        if isinstance(fingerprint, str) and fingerprint:
            groups.setdefault((item.project_id, fingerprint), []).append(item.resolution.candidate_id)
    result: dict[str, str] = {}
    for (_, fingerprint), candidate_ids in groups.items():
        if len(candidate_ids) > 1:
            group = "dup_" + hashlib.sha256(fingerprint.encode("utf-8")).hexdigest()[:16]
            for candidate_id in candidate_ids:
                result[candidate_id] = group
    return result


def build_drafts(
    items: Iterable[RehydratedCandidate], profile: str, estimator: TokenEstimator, render_fragment: Any,
    *, mandatory_roles: frozenset[str] = frozenset(MANDATORY_ROLES),
) -> tuple[CandidateDraft, ...]:
    groups = redundancy_groups(items)
    drafts: list[CandidateDraft] = []
    for item in sorted(items, key=lambda value: value.resolution.candidate_id):
        role = role_for(item)
        tier, mandatory, task_fit = tier_for(role, item.resolution.status, profile, mandatory_roles)
        rendered = render_fragment(item, role)
        estimate = estimator.estimate(rendered)
        utility = UtilityProfile(
            candidate_id=item.resolution.candidate_id,
            role=role,
            tier=tier,
            mandatory=mandatory,
            task_fit=task_fit,
            epistemic_status=item.resolution.status,
            specificity="project_specific" if item.project_id else "global",
            redundancy_group=groups.get(item.resolution.candidate_id),
            estimated_cost=estimate,
        )
        drafts.append(CandidateDraft(item, role, tier, mandatory, task_fit, groups.get(item.resolution.candidate_id), rendered, utility))
    return tuple(drafts)
