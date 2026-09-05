"""Deterministic eligibility, redundancy and constrained-budget selection."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .models import BudgetContract, OmittedItem
from .safety import contains_secret
from .utility import CandidateDraft


ELIGIBLE_STATUSES = frozenset(
    {"AUTHORITATIVE", "SUPPORTING", "IMPLEMENTATION_GAP", "CONTESTED", "UNRESOLVED", "HISTORICAL"}
)
_STATUS_RANK = {
    "AUTHORITATIVE": 0,
    "IMPLEMENTATION_GAP": 1,
    "CONTESTED": 2,
    "UNRESOLVED": 3,
    "SUPPORTING": 4,
    "HISTORICAL": 5,
}


@dataclass(frozen=True)
class SelectionPlan:
    selected: tuple[CandidateDraft, ...]
    omitted: tuple[OmittedItem, ...]
    mandatory_cost: int


def _selection_reason(draft: CandidateDraft) -> str:
    if draft.role == "CONSTRAINT":
        return "mandatory_safety_constraint" if draft.mandatory else "profile_relevant_context"
    if draft.role == "REQUIREMENT":
        return "mandatory_requirement" if draft.mandatory else "profile_relevant_context"
    if draft.role in {"IMPLEMENTATION_GAP", "CONFLICT"}:
        return "mandatory_blocking_issue"
    if draft.tier <= 1:
        return "critical_authoritative_context"
    if draft.tier == 2:
        return "profile_relevant_context"
    if draft.tier == 3:
        return "supporting_context"
    return "optional_context"


def selection_reason(draft: CandidateDraft) -> str:
    return _selection_reason(draft)


def _dedupe(drafts: Iterable[CandidateDraft]) -> tuple[list[CandidateDraft], list[OmittedItem]]:
    groups: dict[str, list[CandidateDraft]] = {}
    ungrouped: list[CandidateDraft] = []
    for draft in drafts:
        if draft.redundancy_group is None:
            ungrouped.append(draft)
        else:
            groups.setdefault(draft.redundancy_group, []).append(draft)
    retained = list(ungrouped)
    omitted: list[OmittedItem] = []
    for values in groups.values():
        winner = min(
            values,
            key=lambda draft: (
                _STATUS_RANK.get(draft.evidence.resolution.status, 99),
                draft.tier,
                draft.evidence.resolution.candidate_id,
            ),
        )
        retained.append(winner)
        for draft in values:
            if draft is not winner:
                omitted.append(
                    OmittedItem(draft.evidence.resolution.candidate_id, "redundant_exact_duplicate", draft.role, draft.tier)
                )
    return retained, omitted


def choose(
    drafts: Iterable[CandidateDraft], budget: BudgetContract, *, allow_history: bool, base_cost: int,
    optional_budget_percent: int | None = None, max_optional_items: int | None = None,
) -> SelectionPlan:
    """Select all mandatory information before optional value, with stable ties."""
    eligible: list[CandidateDraft] = []
    omitted: list[OmittedItem] = []
    for draft in drafts:
        candidate_id = draft.evidence.resolution.candidate_id
        status = draft.evidence.resolution.status
        if status not in ELIGIBLE_STATUSES:
            omitted.append(OmittedItem(candidate_id, "ineligible_lifecycle", draft.role, draft.tier))
        elif status == "HISTORICAL" and not allow_history:
            omitted.append(OmittedItem(candidate_id, "historical_not_requested", draft.role, draft.tier))
        elif contains_secret(draft.evidence.text):
            omitted.append(OmittedItem(candidate_id, "sensitive_content_detected", draft.role, draft.tier))
        else:
            eligible.append(draft)
    eligible, duplicate_omissions = _dedupe(eligible)
    omitted.extend(duplicate_omissions)
    mandatory = sorted((draft for draft in eligible if draft.mandatory), key=lambda draft: (draft.tier, draft.evidence.resolution.candidate_id))
    mandatory_cost = base_cost + sum(draft.utility.estimated_cost.count for draft in mandatory)
    if mandatory_cost > budget.usable_tokens:
        omitted.extend(
            OmittedItem(draft.evidence.resolution.candidate_id, "mandatory_overflow", draft.role, draft.tier)
            for draft in mandatory
        )
        return SelectionPlan((), tuple(sorted(omitted, key=lambda item: item.candidate_id)), mandatory_cost)

    selected = list(mandatory)
    spent = mandatory_cost
    if optional_budget_percent is None:
        optional_limit = budget.usable_tokens - mandatory_cost
    else:
        optional_limit = min(
            budget.usable_tokens - mandatory_cost,
            budget.usable_tokens * optional_budget_percent // 100,
        )
    optional_spent = 0
    optional_count = 0
    optional = sorted(
        (draft for draft in eligible if not draft.mandatory),
        key=lambda draft: (draft.tier, _STATUS_RANK.get(draft.evidence.resolution.status, 99), draft.evidence.resolution.candidate_id),
    )
    for draft in optional:
        cost = draft.utility.estimated_cost.count
        if (
            spent + cost <= budget.usable_tokens
            and optional_spent + cost <= optional_limit
            and (max_optional_items is None or optional_count < max_optional_items)
        ):
            selected.append(draft)
            spent += cost
            optional_spent += cost
            optional_count += 1
        else:
            reason = "budget_exhausted"
            if optional_budget_percent is not None and optional_spent + cost > optional_limit:
                reason = "profile_budget_exhausted"
            elif max_optional_items is not None and optional_count >= max_optional_items:
                reason = "profile_item_limit"
            omitted.append(OmittedItem(draft.evidence.resolution.candidate_id, reason, draft.role, draft.tier))
    return SelectionPlan(
        tuple(sorted(selected, key=lambda draft: (draft.tier, draft.evidence.resolution.candidate_id))),
        tuple(sorted(omitted, key=lambda item: item.candidate_id)),
        mandatory_cost,
    )
