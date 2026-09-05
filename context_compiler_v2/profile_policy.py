"""Deterministic, task-profile-aware budget policy for Compiler V2.

The policy only partitions the caller-owned budget between mandatory and
optional context.  It never lowers a mandatory allocation and never changes
scope, authority or lifecycle decisions.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


PROFILE_NAMES = frozenset(
    {"continuation", "implementation", "debugging", "architecture", "review", "research", "general"}
)
MANDATORY_ROLES = ("CONSTRAINT", "REQUIREMENT", "IMPLEMENTATION_GAP", "CONFLICT")


@dataclass(frozen=True)
class ProfileBudgetPolicy:
    """A bounded optional-context policy; mandatory context is always first."""

    optional_budget_percent: int
    max_optional_items: int
    mandatory_roles: tuple[str, ...] = MANDATORY_ROLES

    def __post_init__(self) -> None:
        if isinstance(self.optional_budget_percent, bool) or not isinstance(self.optional_budget_percent, int):
            raise ValueError("profile budget optional_budget_percent must be an integer")
        if not 0 <= self.optional_budget_percent <= 100:
            raise ValueError("profile budget optional_budget_percent must be 0..100")
        if isinstance(self.max_optional_items, bool) or not isinstance(self.max_optional_items, int):
            raise ValueError("profile budget max_optional_items must be an integer")
        if not 0 <= self.max_optional_items <= 256:
            raise ValueError("profile budget max_optional_items must be 0..256")
        roles = tuple(self.mandatory_roles)
        if not roles or len(roles) != len(set(roles)) or any(role not in MANDATORY_ROLES for role in roles):
            raise ValueError("profile budget mandatory_roles are invalid")
        object.__setattr__(self, "mandatory_roles", tuple(sorted(roles)))

    def optional_budget(self, usable_tokens: int, mandatory_cost: int) -> int:
        """Return optional capacity after mandatory allocation, never negative."""
        remaining = max(0, usable_tokens - mandatory_cost)
        profile_cap = usable_tokens * self.optional_budget_percent // 100
        return min(remaining, profile_cap)

    def to_dict(self) -> dict[str, Any]:
        return {
            "optional_budget_percent": self.optional_budget_percent,
            "max_optional_items": self.max_optional_items,
            "mandatory_roles": list(self.mandatory_roles),
        }


DEFAULT_PROFILE_BUDGETS: Mapping[str, ProfileBudgetPolicy] = {
    "continuation": ProfileBudgetPolicy(40, 16),
    "implementation": ProfileBudgetPolicy(65, 32),
    "debugging": ProfileBudgetPolicy(55, 24),
    "architecture": ProfileBudgetPolicy(70, 40),
    "review": ProfileBudgetPolicy(55, 24),
    "research": ProfileBudgetPolicy(60, 32),
    "general": ProfileBudgetPolicy(50, 24),
}


def profile_budgets_from_dict(value: Any) -> dict[str, ProfileBudgetPolicy]:
    if not isinstance(value, Mapping) or set(value) != PROFILE_NAMES:
        raise ValueError("profile_budgets must define every supported compiler profile")
    result: dict[str, ProfileBudgetPolicy] = {}
    for name in sorted(PROFILE_NAMES):
        payload = value[name]
        if not isinstance(payload, Mapping) or set(payload) != {
            "optional_budget_percent", "max_optional_items", "mandatory_roles"
        }:
            raise ValueError(f"profile_budgets.{name} has an unsupported schema")
        roles = payload["mandatory_roles"]
        if not isinstance(roles, list):
            raise ValueError(f"profile_budgets.{name}.mandatory_roles must be a list")
        result[name] = ProfileBudgetPolicy(
            payload["optional_budget_percent"], payload["max_optional_items"], tuple(roles)
        )
    return result
