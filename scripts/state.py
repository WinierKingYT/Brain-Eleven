#!/usr/bin/env python3
"""Typed local CLI for Phase 16 project state."""

from __future__ import annotations

import argparse
import json
from typing import Optional, Sequence

from state_resolver import StateResolver
from state_store import (
    StateError,
    StateProjectArchived,
    StateProjectUnknown,
    StateSchemaError,
    StateStoreConflict,
    StateTransitionError,
    StateService,
)


def _source(arguments) -> dict:
    return {"type": arguments.source, "reference": arguments.source_reference}


def _error_code(exc: Exception) -> str:
    if isinstance(exc, StateProjectUnknown):
        return "PROJECT_UNKNOWN"
    if isinstance(exc, StateProjectArchived):
        return "PROJECT_ARCHIVED"
    if isinstance(exc, StateStoreConflict):
        return "STATE_CONFLICT"
    if isinstance(exc, StateTransitionError):
        return "INVALID_TRANSITION"
    if isinstance(exc, StateSchemaError):
        return "INVALID_SCHEMA"
    return "STATE_ERROR"


def _add_common_mutation_arguments(command) -> None:
    command.add_argument("--expected-revision", type=int, required=True)
    command.add_argument("--source", choices=("user", "system", "tool"), default="user")
    command.add_argument("--source-reference")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage typed canonical project state.")
    parser.add_argument("--vault", default=".", help="Vault containing .claude authorities")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable output")
    commands = parser.add_subparsers(dest="command", required=True)

    show = commands.add_parser("show")
    show.add_argument("--project-id", required=True)
    init = commands.add_parser("init")
    init.add_argument("--project-id", required=True)
    init.add_argument("--source", choices=("user", "system", "tool"), default="user")
    init.add_argument("--source-reference")

    set_phase = commands.add_parser("set-phase")
    set_phase.add_argument("--project-id", required=True)
    set_phase.add_argument("--phase-id", required=True)
    set_phase.add_argument("--title", required=True)
    set_phase.add_argument("--record-id")
    _add_common_mutation_arguments(set_phase)

    transition_phase = commands.add_parser("transition-phase")
    transition_phase.add_argument("--project-id", required=True)
    transition_phase.add_argument("--milestone-id", required=True)
    transition_phase.add_argument("--target-status", required=True)
    _add_common_mutation_arguments(transition_phase)

    objective = commands.add_parser("set-objective")
    objective.add_argument("--project-id", required=True)
    objective.add_argument("--text", required=True)
    objective.add_argument("--record-id")
    _add_common_mutation_arguments(objective)

    add_requirement = commands.add_parser("add-requirement")
    add_requirement.add_argument("--project-id", required=True)
    add_requirement.add_argument("--text", required=True)
    add_requirement.add_argument("--record-id")
    _add_common_mutation_arguments(add_requirement)

    resolve_requirement = commands.add_parser("resolve-requirement")
    resolve_requirement.add_argument("--project-id", required=True)
    resolve_requirement.add_argument("--requirement-id", required=True)
    resolve_requirement.add_argument("--cancelled", action="store_true")
    _add_common_mutation_arguments(resolve_requirement)

    add_work = commands.add_parser("add-work-item")
    add_work.add_argument("--project-id", required=True)
    add_work.add_argument("--text", required=True)
    add_work.add_argument("--record-id")
    _add_common_mutation_arguments(add_work)

    transition_work = commands.add_parser("transition-work-item")
    transition_work.add_argument("--project-id", required=True)
    transition_work.add_argument("--work-item-id", required=True)
    transition_work.add_argument("--target-status", required=True)
    _add_common_mutation_arguments(transition_work)

    add_blocker = commands.add_parser("add-blocker")
    add_blocker.add_argument("--project-id", required=True)
    add_blocker.add_argument("--text", required=True)
    add_blocker.add_argument("--severity", required=True)
    add_blocker.add_argument("--record-id")
    add_blocker.add_argument("--memory-ref")
    _add_common_mutation_arguments(add_blocker)

    resolve_blocker = commands.add_parser("resolve-blocker")
    resolve_blocker.add_argument("--project-id", required=True)
    resolve_blocker.add_argument("--blocker-id", required=True)
    _add_common_mutation_arguments(resolve_blocker)

    add_constraint = commands.add_parser("add-constraint")
    add_constraint.add_argument("--project-id", required=True)
    add_constraint.add_argument("--text", required=True)
    add_constraint.add_argument("--record-id")
    _add_common_mutation_arguments(add_constraint)

    add_risk = commands.add_parser("add-risk")
    add_risk.add_argument("--project-id", required=True)
    add_risk.add_argument("--text", required=True)
    add_risk.add_argument("--severity", required=True)
    add_risk.add_argument("--record-id")
    _add_common_mutation_arguments(add_risk)

    add_reference = commands.add_parser("add-memory-reference")
    add_reference.add_argument("--project-id", required=True)
    add_reference.add_argument("--memory-id", required=True)
    _add_common_mutation_arguments(add_reference)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    arguments = parser.parse_args(argv)
    try:
        if arguments.command == "show":
            result = StateResolver(arguments.vault).resolve(arguments.project_id).to_dict()
        else:
            service = StateService(arguments.vault)
            source = _source(arguments)
            if arguments.command == "init":
                result = service.init_project(arguments.project_id, source=source)
            elif arguments.command == "set-phase":
                result = service.set_current_milestone(
                    arguments.project_id,
                    phase_id=arguments.phase_id,
                    title=arguments.title,
                    expected_revision=arguments.expected_revision,
                    source=source,
                    record_id=arguments.record_id,
                )
            elif arguments.command == "transition-phase":
                result = service.transition_milestone(
                    arguments.project_id,
                    milestone_id=arguments.milestone_id,
                    target_status=arguments.target_status,
                    expected_revision=arguments.expected_revision,
                    source=source,
                )
            elif arguments.command == "set-objective":
                result = service.set_current_objective(
                    arguments.project_id,
                    text=arguments.text,
                    expected_revision=arguments.expected_revision,
                    source=source,
                    record_id=arguments.record_id,
                )
            elif arguments.command == "add-requirement":
                result = service.add_requirement(
                    arguments.project_id,
                    text=arguments.text,
                    expected_revision=arguments.expected_revision,
                    source=source,
                    record_id=arguments.record_id,
                )
            elif arguments.command == "resolve-requirement":
                result = service.resolve_requirement(
                    arguments.project_id,
                    requirement_id=arguments.requirement_id,
                    expected_revision=arguments.expected_revision,
                    source=source,
                    cancelled=arguments.cancelled,
                )
            elif arguments.command == "add-work-item":
                result = service.add_work_item(
                    arguments.project_id,
                    text=arguments.text,
                    expected_revision=arguments.expected_revision,
                    source=source,
                    record_id=arguments.record_id,
                )
            elif arguments.command == "transition-work-item":
                result = service.transition_work_item(
                    arguments.project_id,
                    work_item_id=arguments.work_item_id,
                    target_status=arguments.target_status,
                    expected_revision=arguments.expected_revision,
                    source=source,
                )
            elif arguments.command == "add-blocker":
                result = service.add_blocker(
                    arguments.project_id,
                    text=arguments.text,
                    severity=arguments.severity,
                    expected_revision=arguments.expected_revision,
                    source=source,
                    record_id=arguments.record_id,
                    memory_ref=arguments.memory_ref,
                )
            elif arguments.command == "resolve-blocker":
                result = service.resolve_blocker(
                    arguments.project_id,
                    blocker_id=arguments.blocker_id,
                    expected_revision=arguments.expected_revision,
                    source=source,
                )
            elif arguments.command == "add-constraint":
                result = service.add_constraint(
                    arguments.project_id,
                    text=arguments.text,
                    expected_revision=arguments.expected_revision,
                    source=source,
                    record_id=arguments.record_id,
                )
            elif arguments.command == "add-risk":
                result = service.add_risk(
                    arguments.project_id,
                    text=arguments.text,
                    severity=arguments.severity,
                    expected_revision=arguments.expected_revision,
                    source=source,
                    record_id=arguments.record_id,
                )
            elif arguments.command == "add-memory-reference":
                result = service.add_memory_reference(
                    arguments.project_id,
                    memory_id=arguments.memory_id,
                    expected_revision=arguments.expected_revision,
                    source=source,
                )
            else:
                raise AssertionError(f"Unhandled command: {arguments.command}")
        print(json.dumps(result, ensure_ascii=False, indent=2) if arguments.json else result)
        return 0
    except StateError as exc:
        payload = {"error": {"code": _error_code(exc), "message": str(exc)}}
        print(json.dumps(payload, ensure_ascii=False) if arguments.json else f"{payload['error']['code']}: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
