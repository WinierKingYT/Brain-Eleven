"""Deterministic router policy; no raw prompt can widen security scope."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from .models import RouteScope, RouterContractError, RoutingOptions


PROFILE_BY_INTENT = {
    "IMPLEMENT": "implementation",
    "MIGRATE": "implementation",
    "TEST": "implementation",
    "DEBUG": "debugging",
    "REVIEW": "review",
    "PLAN": "architecture",
    "DESIGN": "architecture",
    "RESEARCH": "research",
}
_CONTINUATION = re.compile(r"\b(devam\s+et|kald[ıi]ğ[ıi]m[ıi]z\s+yerden|continue\s+where)\b", re.IGNORECASE)


class ScopePolicyError(RouterContractError):
    """A route attempted to use an unsafe or incoherent source scope."""


def resolve_profile(task) -> str:
    """Map Phase 16 intent into one bounded retrieval profile."""
    if getattr(task, "continuation_of", None) or _CONTINUATION.search(task.raw_request):
        return "continuation"
    return PROFILE_BY_INTENT.get(getattr(task.intent, "value", ""), "general")


def resolve_history_mode(task, options: RoutingOptions) -> str:
    """Return only the caller-authorized lifecycle scope.

    A raw request may affect the retrieval profile and query terms, but must
    never widen history.  Otherwise a phrase such as "look at old decisions"
    could bypass the trusted caller's lifecycle policy.
    """
    del task
    return options.history_mode


def resolve_scope(task, options: RoutingOptions) -> RouteScope:
    """Build a finite scope from trusted options plus resolved task identity."""
    task_project = getattr(getattr(task, "project", None), "project_id", None)
    task_status = getattr(getattr(task, "project", None), "status", None)
    if options.scope_mode == "GLOBAL_ONLY":
        return RouteScope("GLOBAL_ONLY", (), options.include_global)
    if options.scope_mode == "CURRENT_PROJECT":
        if task_status != "resolved" or not task_project:
            raise ScopePolicyError("CURRENT_PROJECT routing requires a resolved task project")
        return RouteScope("CURRENT_PROJECT", (task_project,), options.include_global)
    selected = options.selected_project_ids
    if task_status == "resolved" and task_project not in selected:
        raise ScopePolicyError("SELECTED_PROJECTS must include the resolved task project")
    return RouteScope("SELECTED_PROJECTS", selected, options.include_global)


def lifecycle_allowed(status: str, history_mode: str) -> bool:
    """The only lifecycle policy used by every adapter."""
    if history_mode == "ACTIVE_ONLY":
        return status == "active"
    if history_mode == "ACTIVE_PLUS_RELEVANT_HISTORY":
        return status in {"active", "resolved", "superseded"}
    if history_mode == "HISTORY_ONLY":
        return status in {"resolved", "superseded"}
    raise ScopePolicyError(f"Unknown history policy: {history_mode}")
