"""Read-only rehydration of Router references into canonical metadata."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Optional


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


class AuthorityEvidenceError(RuntimeError):
    """A Router reference cannot be verified against a canonical authority."""


class AuthorityStaleInput(AuthorityEvidenceError):
    """The Router snapshot is not the canonical snapshot authority must use."""


@dataclass(frozen=True)
class EvidenceItem:
    candidate: Any
    record: Mapping[str, Any]
    project_id: Optional[str]
    state_kind: Optional[str] = None


@dataclass(frozen=True)
class EvidenceSnapshot:
    revisions: Mapping[str, Any]
    memory_records: Mapping[str, Mapping[str, Any]]
    states: Mapping[str, CurrentProjectState]
    items: tuple[EvidenceItem, ...]


class AuthorityEvidenceAdapter:
    """Rehydrate only Router-selected canonical references, never retrieve."""

    def __init__(self, vault_path: str | Path):
        self.vault_path = Path(vault_path)
        self.memory = MemoryStore(self.vault_path)
        self.state = StateResolver(self.vault_path)

    @staticmethod
    def _expected_memory_revision(router_result: Any) -> int:
        revision = router_result.input_revisions.get("memory")
        if isinstance(revision, bool) or not isinstance(revision, int) or revision < 0:
            raise AuthorityEvidenceError("RouterResult has no valid memory revision")
        return revision

    @staticmethod
    def _expected_state_revisions(router_result: Any) -> Mapping[str, Any]:
        value = router_result.input_revisions.get("state")
        if not isinstance(value, Mapping):
            raise AuthorityEvidenceError("RouterResult has no valid state revision map")
        for project_id, details in value.items():
            if not isinstance(project_id, str) or not project_id or not isinstance(details, Mapping):
                raise AuthorityEvidenceError("RouterResult has malformed state revision metadata")
            revision = details.get("revision")
            if revision is not None and (isinstance(revision, bool) or not isinstance(revision, int) or revision < 0):
                raise AuthorityEvidenceError("RouterResult has malformed state revision")
            if not isinstance(details.get("status"), str):
                raise AuthorityEvidenceError("RouterResult has malformed state status")
        return value

    @staticmethod
    def _state_item(state: CurrentProjectState, kind: str, item_id: str) -> Mapping[str, Any]:
        current = state.current
        if kind in {"objective", "milestone"}:
            item = current.get(kind)
            if isinstance(item, Mapping) and str(item.get("id") or kind) == item_id:
                return item
        collections = {
            "blocker": state.active_blockers,
            "requirement": state.active_requirements,
            "work_item": state.active_work_items,
            "constraint": state.constraints,
            "risk": state.risks,
        }
        for item in collections.get(kind, ()):  # unknown kinds remain invalid
            if str(item.get("id") or kind) == item_id:
                return item
        raise AuthorityEvidenceError(f"State item is not current: {kind}:{item_id}")

    def _load_states(self, expected: Mapping[str, Any]) -> dict[str, CurrentProjectState]:
        states: dict[str, CurrentProjectState] = {}
        for project_id, details in sorted(expected.items()):
            state = self.state.resolve(project_id)
            if state.status in {STATE_CORRUPT, STATE_UNAVAILABLE, PROJECT_UNKNOWN}:
                raise AuthorityEvidenceError(f"Canonical state unavailable for {project_id}: {state.status}")
            if state.status == PROJECT_ARCHIVED:
                raise AuthorityEvidenceError(f"Archived state requires explicit history permission: {project_id}")
            if state.status != details["status"] or state.state_revision != details.get("revision"):
                raise AuthorityStaleInput(f"State revision changed for {project_id}")
            states[project_id] = state
        return states

    @staticmethod
    def _memory_item(candidate: Any, records: Mapping[str, Mapping[str, Any]], revision: int) -> EvidenceItem:
        reference = candidate.canonical_ref
        if reference.get("authority") != "memory":
            raise AuthorityEvidenceError("Memory candidate has an invalid canonical authority")
        memory_id = reference.get("memory_id")
        if not isinstance(memory_id, str) or memory_id != candidate.candidate_id:
            raise AuthorityEvidenceError("Memory candidate canonical reference does not match candidate ID")
        if candidate.source_revision != revision:
            raise AuthorityStaleInput("Memory candidate revision differs from Router snapshot")
        record = records.get(memory_id)
        if record is None:
            raise AuthorityEvidenceError(f"Router returned unknown memory: {memory_id}")
        scope, _, project_id = infer_memory_scope(dict(record))
        expected_project = project_id if scope == "project" else None
        if candidate.project_id != expected_project:
            raise AuthorityEvidenceError(f"Memory project provenance mismatch: {memory_id}")
        if candidate.content_type != str(record.get("type", "unknown")):
            raise AuthorityEvidenceError(f"Memory type mismatch: {memory_id}")
        if candidate.lifecycle.casefold() != str(record.get("status", "active")).casefold():
            raise AuthorityEvidenceError(f"Memory lifecycle mismatch: {memory_id}")
        return EvidenceItem(candidate=candidate, record=record, project_id=expected_project)

    @classmethod
    def _state_evidence(cls, candidate: Any, states: Mapping[str, CurrentProjectState]) -> EvidenceItem:
        reference = candidate.canonical_ref
        required = {"authority", "project_id", "state_revision", "kind", "item_id"}
        if set(reference) != required or reference.get("authority") != "state":
            raise AuthorityEvidenceError("State candidate has an invalid canonical reference")
        project_id = reference["project_id"]
        state = states.get(project_id)
        if state is None:
            raise AuthorityEvidenceError(f"State candidate project is outside Router snapshot: {project_id}")
        if candidate.project_id != project_id or candidate.source_revision != state.state_revision:
            raise AuthorityStaleInput(f"State candidate revision differs from Router snapshot: {candidate.candidate_id}")
        if reference["state_revision"] != state.state_revision:
            raise AuthorityStaleInput(f"State canonical reference is stale: {candidate.candidate_id}")
        kind = reference["kind"]
        item = cls._state_item(state, kind, reference["item_id"])
        if candidate.content_type != kind or candidate.lifecycle.casefold() != str(item.get("status", "active")).casefold():
            raise AuthorityEvidenceError(f"State candidate metadata mismatch: {candidate.candidate_id}")
        return EvidenceItem(candidate=candidate, record=item, project_id=project_id, state_kind=kind)

    def snapshot(self, router_result: Any) -> EvidenceSnapshot:
        expected_memory_revision = self._expected_memory_revision(router_result)
        expected_states = self._expected_state_revisions(router_result)
        try:
            document = self.memory.load()
        except MemoryStoreError as exc:
            raise AuthorityEvidenceError(f"Canonical memory unavailable: {exc}") from exc
        if document.get("revision") != expected_memory_revision:
            raise AuthorityStaleInput("Memory revision differs from Router snapshot")
        raw_records = document.get("validated_memory")
        if not isinstance(raw_records, list):
            raise AuthorityEvidenceError("Canonical memory records are invalid")
        records = {
            str(record.get("memory_id")): record
            for record in raw_records
            if isinstance(record, Mapping) and isinstance(record.get("memory_id"), str) and record.get("memory_id")
        }
        states = self._load_states(expected_states)
        items: list[EvidenceItem] = []
        for candidate in router_result.candidates:
            if candidate.source_type == "memory":
                items.append(self._memory_item(candidate, records, expected_memory_revision))
            elif candidate.source_type == "state":
                items.append(self._state_evidence(candidate, states))
            else:
                raise AuthorityEvidenceError(f"Unsupported Router candidate source: {candidate.source_type}")
        return EvidenceSnapshot(
            revisions={"memory": expected_memory_revision, "state": dict(expected_states)},
            memory_records=records,
            states=states,
            items=tuple(items),
        )

    def inputs_current(self, snapshot: EvidenceSnapshot) -> bool:
        try:
            if self.memory.revision() != snapshot.revisions["memory"]:
                return False
            for project_id, details in snapshot.revisions["state"].items():
                state = self.state.resolve(project_id)
                if state.status != details["status"] or state.state_revision != details.get("revision"):
                    return False
        except (MemoryStoreError, OSError):
            return False
        return True
