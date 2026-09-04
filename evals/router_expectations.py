"""Strict, independent route-quality labels for the Phase 17 router."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


ROUTER_EXPECTATION_SCHEMA_VERSION = 1
DEFAULT_ROUTER_EXPECTATIONS = Path(__file__).resolve().parent / "fixtures" / "phase17-router-expectations.json"


class RouterExpectationError(ValueError):
    pass


@dataclass(frozen=True)
class RouterExpectation:
    case_id: str
    project_id: str | None
    request: str
    options: Mapping[str, Any]
    profile: str
    scope_mode: str
    history_mode: str
    required_sources: tuple[str, ...]
    forbidden_project_ids: tuple[str, ...]


def _string(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RouterExpectationError(f"{name} must be a non-empty string")
    return value.strip()


def _strings(value: Any, name: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(item, str) and item.strip() for item in value):
        raise RouterExpectationError(f"{name} must be a non-empty string list")
    result = tuple(value)
    if len(set(result)) != len(result):
        raise RouterExpectationError(f"{name} must not contain duplicates")
    return result


def load_router_expectations(path: Path | str = DEFAULT_ROUTER_EXPECTATIONS) -> tuple[RouterExpectation, ...]:
    try:
        document = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RouterExpectationError(f"Cannot read router expectation sidecar: {path}") from exc
    if not isinstance(document, Mapping) or set(document) != {"schema_version", "cases"}:
        raise RouterExpectationError("Router expectation sidecar has an invalid envelope")
    if document["schema_version"] != ROUTER_EXPECTATION_SCHEMA_VERSION:
        raise RouterExpectationError("Unsupported router expectation schema")
    cases = document["cases"]
    if not isinstance(cases, list) or not cases:
        raise RouterExpectationError("Router expectation sidecar requires cases")
    parsed = []
    case_ids = set()
    for index, case in enumerate(cases):
        if not isinstance(case, Mapping) or set(case) != {"case_id", "project_id", "request", "options", "expected"}:
            raise RouterExpectationError(f"cases[{index}] has invalid fields")
        expected = case["expected"]
        if not isinstance(expected, Mapping) or set(expected) != {
            "profile", "scope_mode", "history_mode", "required_sources", "forbidden_project_ids"
        }:
            raise RouterExpectationError(f"cases[{index}].expected has invalid fields")
        case_id = _string(case["case_id"], f"cases[{index}].case_id")
        if case_id in case_ids:
            raise RouterExpectationError(f"duplicate router case_id: {case_id}")
        case_ids.add(case_id)
        project_id = case["project_id"]
        if project_id is not None:
            project_id = _string(project_id, f"cases[{index}].project_id")
        if not isinstance(case["options"], Mapping):
            raise RouterExpectationError(f"cases[{index}].options must be an object")
        parsed.append(
            RouterExpectation(
                case_id=case_id,
                project_id=project_id,
                request=_string(case["request"], f"cases[{index}].request"),
                options=dict(case["options"]),
                profile=_string(expected["profile"], f"cases[{index}].expected.profile"),
                scope_mode=_string(expected["scope_mode"], f"cases[{index}].expected.scope_mode"),
                history_mode=_string(expected["history_mode"], f"cases[{index}].expected.history_mode"),
                required_sources=_strings(expected["required_sources"], f"cases[{index}].expected.required_sources"),
                forbidden_project_ids=_strings(
                    expected["forbidden_project_ids"], f"cases[{index}].expected.forbidden_project_ids"
                ),
            )
        )
    return tuple(parsed)
