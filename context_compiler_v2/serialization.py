"""Strict decoding for Phase 19 CLI inputs; content enters only via canonical reads."""

from __future__ import annotations

from typing import Any, Mapping

from authority.serialization import resolution_result_from_dict, task_state_from_dict

from .models import BudgetContract, CompilationRequest


def _mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be an object")
    return value


def compilation_request_from_dict(document: Mapping[str, Any]) -> CompilationRequest:
    document = _mapping(document, "compilation_request")
    required = {"schema_version", "task_state", "resolution_result", "budget"}
    if set(document) - (required | {"compiler_profile"}) or required - set(document):
        raise ValueError("compilation_request fields are invalid")
    if document["schema_version"] != 1:
        raise ValueError("compilation_request schema_version is unsupported")
    budget_data = _mapping(document["budget"], "compilation_request.budget")
    allowed = {
        "max_context_tokens", "minimum_headroom_tokens", "hard_byte_limit", "estimation_mode",
        "mandatory_overflow_policy", "allow_optional_omission",
    }
    if set(budget_data) - allowed or "max_context_tokens" not in budget_data:
        raise ValueError("compilation_request.budget fields are invalid")
    budget = BudgetContract(**dict(budget_data))
    profile = document.get("compiler_profile")
    return CompilationRequest(
        task_state_from_dict(_mapping(document["task_state"], "compilation_request.task_state")),
        resolution_result_from_dict(_mapping(document["resolution_result"], "compilation_request.resolution_result")),
        budget,
        profile,
    )
