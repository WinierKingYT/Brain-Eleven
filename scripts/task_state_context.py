#!/usr/bin/env python3
"""Compose a runtime TaskEnvelope and CurrentProjectState without routing."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Optional, Sequence

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from brain_eleven.state.resolver import CurrentProjectState, StateResolver
from task_model import TaskAnalyzer, TaskEnvelope, TaskProjectResolutionError, TaskValidationError


TASK_STATE_CONTEXT_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class TaskStateContext:
    """The complete Phase 17 input contract, minus any retrieval decision."""

    task: TaskEnvelope
    state: CurrentProjectState

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": TASK_STATE_CONTEXT_SCHEMA_VERSION,
            "task": self.task.to_dict(),
            "state": self.state.to_dict(),
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
        task = self.analyzer.analyze(raw_request)
        state = self.resolver.resolve(task.project.project_id or "")
        return TaskStateContext(task=self._merge_task_state(task, state), state=state)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Compose task and current state without retrieval.")
    parser.add_argument("--vault", default=".", help="Vault containing local authorities")
    parser.add_argument("--project-root", default=".", help="Project root for registry resolution")
    parser.add_argument("--request", required=True, help="Raw user request")
    parser.add_argument("--json", action="store_true", help="Emit the machine contract")
    arguments = parser.parse_args(argv)
    try:
        context = TaskStateComposer(arguments.vault, arguments.project_root).compose(arguments.request)
    except (TaskValidationError, TaskProjectResolutionError) as exc:
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
