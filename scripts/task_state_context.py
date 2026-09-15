#!/usr/bin/env python3
"""Compose a runtime TaskEnvelope and CurrentProjectState without routing."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

from brain_eleven.projects.identity import (
    ROOT_IDENTITY_PATTERN,
    ProjectLineageError,
    project_root_identity,
    registry_snapshot_for_root,
)
from brain_eleven.state.resolver import CurrentProjectState, StateResolver
try:
    from scripts.task_model import TaskAnalyzer, TaskEnvelope, TaskProjectResolutionError, TaskValidationError
except ModuleNotFoundError as exc:  # pragma: no cover - deployed copied-hook fallback
    if exc.name != "scripts":
        raise
    from task_model import TaskAnalyzer, TaskEnvelope, TaskProjectResolutionError, TaskValidationError


# Schema 1 remains the stable outer task/state envelope for existing callers.
# TSC-02 makes the lineage member mandatory for current-project contexts under
# this explicit schema-1-with-lineage policy; an old schema-1 payload without
# lineage is never accepted by the router or authority.
TASK_STATE_CONTEXT_SCHEMA_VERSION = 1
LINEAGE_STATUSES = frozenset({"resolved", "unresolved", "global"})


class TaskStateLineageError(RuntimeError):
    """The registry changed while a read-only task/state context was built."""


@dataclass(frozen=True)
class TaskStateLineage:
    """Content-free project identity observed while composing a context."""

    status: str = "resolved"
    project_id: Optional[str] = None
    registry_revision: Optional[int] = None
    root_identity: Optional[str] = None

    def __post_init__(self) -> None:
        if self.status not in LINEAGE_STATUSES:
            raise ValueError("lineage.status is unsupported")
        if self.status in {"unresolved", "global"}:
            if any(value is not None for value in (self.project_id, self.registry_revision, self.root_identity)):
                raise ValueError("non-resolved lineage must not carry project identity")
            return
        if not isinstance(self.project_id, str) or not self.project_id.strip():
            raise ValueError("lineage.project_id is invalid")
        if (
            isinstance(self.registry_revision, bool)
            or not isinstance(self.registry_revision, int)
            or self.registry_revision < 0
        ):
            raise ValueError("lineage.registry_revision is invalid")
        if not isinstance(self.root_identity, str) or not ROOT_IDENTITY_PATTERN.fullmatch(self.root_identity):
            raise ValueError("lineage.root_identity is invalid")

    @classmethod
    def from_dict(cls, document: Any) -> "TaskStateLineage":
        if not isinstance(document, Mapping):
            raise ValueError("task_state.lineage must be an object")
        if document.get("status") in {"unresolved", "global"}:
            if set(document) != {"status"}:
                raise ValueError("task_state.lineage fields are invalid")
            return cls(status=document["status"])
        if set(document) != {"project_id", "registry_revision", "root_identity"}:
            raise ValueError("task_state.lineage fields are invalid")
        return cls(
            project_id=document["project_id"],
            registry_revision=document["registry_revision"],
            root_identity=document["root_identity"],
        )

    def to_dict(self) -> dict[str, Any]:
        if self.status in {"unresolved", "global"}:
            return {"status": self.status}
        return {
            "project_id": self.project_id,
            "registry_revision": self.registry_revision,
            "root_identity": self.root_identity,
        }


@dataclass(frozen=True)
class TaskStateContext:
    """The complete Phase 17 input contract, minus any retrieval decision."""

    task: TaskEnvelope
    state: CurrentProjectState
    lineage: Optional[TaskStateLineage] = None

    def to_dict(self) -> dict[str, Any]:
        if self.lineage is None:
            raise TaskStateLineageError("TaskStateContext lineage is required")
        return {
            "schema_version": TASK_STATE_CONTEXT_SCHEMA_VERSION,
            "task": self.task.to_dict(),
            "state": self.state.to_dict(),
            "lineage": self.lineage.to_dict(),
        }


class TaskStateComposer:
    """Build one non-persistent context input from task and state authorities."""

    def __init__(self, vault_path: str | Path, project_root: str | Path):
        self.vault_path = Path(vault_path)
        self.project_root = Path(project_root)
        self.analyzer = TaskAnalyzer(self.vault_path, self.project_root)
        self.resolver = StateResolver(self.vault_path)

    @staticmethod
    def _merge_task_state(task: TaskEnvelope, state: CurrentProjectState) -> TaskEnvelope:
        inherited = tuple(
            dict.fromkeys(
                constraint["text"]
                for constraint in state.constraints
                if constraint["text"] not in task.explicit_constraints
            )
        )
        needs = list(task.context_needs)
        if state.active_blockers:
            needs.append("active_blockers")
        if state.references.get("valid"):
            needs.append("state_references")
        merged = replace(
            task,
            inherited_constraints=inherited,
            context_needs=tuple(dict.fromkeys(needs)),
        )
        return TaskEnvelope.from_dict(merged.to_dict())

    def compose(self, raw_request: str) -> TaskStateContext:
        try:
            initial = registry_snapshot_for_root(self.vault_path, self.project_root)
            task = self.analyzer.analyze(raw_request)
            state = self.resolver.resolve(task.project.project_id or "")
            final = registry_snapshot_for_root(self.vault_path, self.project_root)
        except ProjectLineageError as exc:
            raise TaskStateLineageError("Project lineage is unavailable") from exc

        # The analyzer and resolver are intentionally separate legacy reads.
        # Do not publish a mixed context when the registry changes between
        # those reads, including a root reused by a different project.
        if (
            initial.status != final.status
            or initial.project_id != final.project_id
            or initial.normalized_root != final.normalized_root
            or initial.registry_revision != final.registry_revision
        ):
            raise TaskStateLineageError("Project registry changed during context composition")

        if initial.status == "unresolved":
            if task.project.project_id is not None or state.project_id is not None:
                raise TaskStateLineageError("Project lineage does not match task state")
            lineage = TaskStateLineage(status="unresolved")
        else:
            if (
                task.project.project_id != initial.project_id
                or state.project_id != initial.project_id
                or final.root_identity is None
            ):
                raise TaskStateLineageError("Project lineage does not match task state")
            try:
                lineage = TaskStateLineage(
                    project_id=initial.project_id,
                    registry_revision=final.registry_revision,
                    root_identity=project_root_identity(final.normalized_root or self.project_root),
                )
            except (TypeError, ValueError, ProjectLineageError) as exc:
                raise TaskStateLineageError("Project lineage is invalid") from exc

        return TaskStateContext(
            task=self._merge_task_state(task, state),
            state=state,
            lineage=lineage,
        )


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Compose task and current state without retrieval.")
    parser.add_argument("--vault", default=".", help="Vault containing local authorities")
    parser.add_argument("--project-root", default=".", help="Project root for registry resolution")
    parser.add_argument("--request", required=True, help="Raw user request")
    parser.add_argument("--json", action="store_true", help="Emit the machine contract")
    arguments = parser.parse_args(argv)
    try:
        context = TaskStateComposer(arguments.vault, arguments.project_root).compose(arguments.request)
    except (TaskValidationError, TaskProjectResolutionError, TaskStateLineageError) as exc:
        print(json.dumps({"error": {"code": "TASK_STATE_ERROR", "message": str(exc)}}))
        return 2
    payload = context.to_dict()
    if arguments.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(
            f"Project: {payload['task']['project']['project_id'] or 'unresolved'}\n"
            f"Intent: {payload['task']['intent']['value']}\n"
            f"State: {payload['state']['status']}\n"
            f"Phase: {payload['state']['current']['phase_id'] or 'unknown'}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
