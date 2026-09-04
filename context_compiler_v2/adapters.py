"""Read canonical sources only after Phase 18 has resolved their authority."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Optional

from authority.adapters import AuthorityEvidenceAdapter


_ROOT = Path(__file__).resolve().parents[1]
_SCRIPTS = _ROOT / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from memory_scope import infer_memory_scope  # noqa: E402
from memory_store import MemoryStore, MemoryStoreError  # noqa: E402
from state_resolver import (  # noqa: E402
    PROJECT_ARCHIVED,
    PROJECT_UNKNOWN,
    STATE_AVAILABLE,
    STATE_CORRUPT,
    STATE_UNAVAILABLE,
    CurrentProjectState,
    StateResolver,
)


class CompilerEvidenceError(RuntimeError):
    """A resolution cannot be safely rehydrated from canonical authority."""


class CompilerStaleInput(CompilerEvidenceError):
    """Canonical revisions no longer match Phase 18's pinned input."""


class CompilerScopeError(CompilerEvidenceError):
    """A Phase 17/18 project isolation guarantee was violated upstream."""


@dataclass(frozen=True)
class RehydratedCandidate:
    resolution: Any
    record: Mapping[str, Any]
    text: str
    project_id: Optional[str]
    state_kind: Optional[str] = None


@dataclass(frozen=True)
class CompilerSnapshot:
    revisions: Mapping[str, Any]
    candidates: tuple[RehydratedCandidate, ...]


def _state_text(record: Mapping[str, Any], kind: str) -> str:
    """Typed state records have compact text fields, never arbitrary JSON dumps."""
    for field in ("text", "title", "description", "name"):
        value = record.get(field)
        if isinstance(value, str) and value.strip():
            return value.strip()
    if kind == "objective":
        value = record.get("objective")
        if isinstance(value, str) and value.strip():
            return value.strip()
    if kind == "milestone":
        phase = record.get("phase_id")
        title = record.get("title")
        values = [value for value in (phase, title) if isinstance(value, str) and value.strip()]
        if values:
            return " — ".join(values)
    raise CompilerEvidenceError(f"State item has no renderable typed text: {kind}")


class CompilerEvidenceAdapter:
    """Rehydrate only Phase 18 references; never search for more candidates."""

    def __init__(self, vault_path: str | Path):
        self.vault_path = Path(vault_path)
        self.memory = MemoryStore(self.vault_path)
        self.state = StateResolver(self.vault_path)

    @staticmethod
    def _expected_revisions(resolution_result: Any) -> tuple[int, Mapping[str, Any]]:
        revisions = resolution_result.input_revisions
        if not isinstance(revisions, Mapping):
            raise CompilerEvidenceError("Resolution input revisions are invalid")
        memory = revisions.get("memory")
        states = revisions.get("state")
        if isinstance(memory, bool) or not isinstance(memory, int) or memory < 0:
            raise CompilerEvidenceError("Resolution memory revision is invalid")
        if not isinstance(states, Mapping):
            raise CompilerEvidenceError("Resolution state revisions are invalid")
        return memory, states

    @staticmethod
    def _load_state_item(state: CurrentProjectState, reference: Mapping[str, Any]) -> Mapping[str, Any]:
        kind = reference.get("kind")
        item_id = reference.get("item_id")
        if not isinstance(kind, str) or not isinstance(item_id, str):
            raise CompilerEvidenceError("State reference kind/item_id is invalid")
        return AuthorityEvidenceAdapter._state_item(state, kind, item_id)

    def _load_states(self, expected: Mapping[str, Any]) -> Mapping[str, CurrentProjectState]:
        values: dict[str, CurrentProjectState] = {}
        for project_id, details in sorted(expected.items()):
            if not isinstance(project_id, str) or not project_id or not isinstance(details, Mapping):
                raise CompilerEvidenceError("Resolution state revisions are malformed")
            state = self.state.resolve(project_id)
            if state.status in {STATE_CORRUPT, STATE_UNAVAILABLE, PROJECT_UNKNOWN}:
                raise CompilerEvidenceError(f"Canonical state unavailable for {project_id}: {state.status}")
            if state.status == PROJECT_ARCHIVED:
                raise CompilerEvidenceError(f"Archived state cannot enter current context: {project_id}")
            if state.status != STATE_AVAILABLE:
                raise CompilerEvidenceError(f"State is not available for {project_id}: {state.status}")
            if state.status != details.get("status") or state.state_revision != details.get("revision"):
                raise CompilerStaleInput(f"State revision changed for {project_id}")
            values[project_id] = state
        return values

    def snapshot(self, task_state: Any, resolution_result: Any) -> CompilerSnapshot:
        task_project = task_state.task.project.project_id
        if task_project is not None and (not isinstance(task_project, str) or not task_project):
            raise CompilerScopeError("Task project identity is invalid")
        if task_state.state.project_id != task_project:
            raise CompilerScopeError("Task and StateSnapshot project mismatch")
        memory_revision, expected_states = self._expected_revisions(resolution_result)
        try:
            memory_document = self.memory.load()
        except MemoryStoreError as exc:
            raise CompilerEvidenceError(f"Canonical memory unavailable: {exc}") from exc
        if memory_document.get("revision") != memory_revision:
            raise CompilerStaleInput("Memory revision differs from ResolutionResult")
        raw_records = memory_document.get("validated_memory")
        if not isinstance(raw_records, list):
            raise CompilerEvidenceError("Canonical memory records are invalid")
        records = {
            item.get("memory_id"): item
            for item in raw_records
            if isinstance(item, Mapping) and isinstance(item.get("memory_id"), str) and item.get("memory_id")
        }
        states = self._load_states(expected_states)
        items: list[RehydratedCandidate] = []
        for candidate in resolution_result.candidates:
            if candidate.source_type == "memory":
                reference = candidate.canonical_ref
                memory_id = reference.get("memory_id")
                if reference.get("authority") != "memory" or memory_id != candidate.candidate_id:
                    raise CompilerEvidenceError("Resolution memory reference is invalid")
                record = records.get(memory_id)
                if record is None:
                    raise CompilerEvidenceError(f"Resolution references unknown memory: {memory_id}")
                scope, _, project_id = infer_memory_scope(dict(record))
                expected_project = project_id if scope == "project" else None
                if candidate.project_id != expected_project:
                    raise CompilerEvidenceError(f"Resolution provenance mismatch: {memory_id}")
                if expected_project is not None and expected_project != task_project:
                    raise CompilerScopeError(f"UPSTREAM_INVARIANT_VIOLATION: wrong project {memory_id}")
                text = record.get("content")
                if not isinstance(text, str) or not text.strip():
                    raise CompilerEvidenceError(f"Memory content is invalid: {memory_id}")
                items.append(RehydratedCandidate(candidate, record, text.strip(), expected_project))
                continue
            if candidate.source_type == "state":
                reference = candidate.canonical_ref
                project_id = reference.get("project_id")
                if reference.get("authority") != "state" or project_id != candidate.project_id:
                    raise CompilerEvidenceError("Resolution state reference is invalid")
                if project_id != task_project:
                    raise CompilerScopeError("UPSTREAM_INVARIANT_VIOLATION: wrong project state")
                state = states.get(project_id)
                if state is None or reference.get("state_revision") != state.state_revision:
                    raise CompilerStaleInput("State reference differs from canonical state")
                record = self._load_state_item(state, reference)
                kind = reference["kind"]
                items.append(RehydratedCandidate(candidate, record, _state_text(record, kind), project_id, kind))
                continue
            raise CompilerEvidenceError(f"Unsupported resolved source: {candidate.source_type}")
        return CompilerSnapshot(
            revisions={"memory": memory_revision, "state": dict(expected_states)},
            candidates=tuple(sorted(items, key=lambda item: item.resolution.candidate_id)),
        )

    def inputs_current(self, snapshot: CompilerSnapshot) -> bool:
        try:
            if self.memory.revision() != snapshot.revisions["memory"]:
                return False
            for project_id, details in snapshot.revisions["state"].items():
                state = self.state.resolve(project_id)
                if state.status != details.get("status") or state.state_revision != details.get("revision"):
                    return False
        except (MemoryStoreError, OSError):
            return False
        return True
