"""Read-only adapters over canonical memory, structured state, and graph projection."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional

_ROOT = Path(__file__).resolve().parents[1]
_SCRIPTS = _ROOT / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from brain_eleven.graph import KnowledgeGraph  # noqa: E402
from brain_eleven.memory.scope import infer_memory_scope  # noqa: E402
from brain_eleven.memory import MemoryStore, MemoryStoreError  # noqa: E402
from brain_eleven.projects.registry import (  # noqa: E402
    ProjectRegistry,
    ProjectRegistryError,
)
from state_resolver import (  # noqa: E402
    PROJECT_ARCHIVED,
    PROJECT_UNKNOWN,
    STATE_AVAILABLE,
    STATE_CORRUPT,
    STATE_NOT_FOUND,
    STATE_UNAVAILABLE,
    CurrentProjectState,
    StateResolver,
)

from .models import RetrievalQuery, RouteScope
from .policy import lifecycle_allowed


@dataclass(frozen=True)
class RawCandidate:
    candidate_id: str
    source_type: str
    project_id: Optional[str]
    content_type: str
    lifecycle: str
    source_revision: Optional[int]
    canonical_ref: Mapping[str, Any]
    query_id: str
    signal: str
    score: float


class MemoryAdapter:
    """Snapshot and search canonical memory without modifying it."""

    def __init__(self, vault_path: str | Path):
        self.store = MemoryStore(vault_path)

    def snapshot(self) -> tuple[int, tuple[Mapping[str, Any], ...]]:
        document = self.store.load()
        revision = document.get("revision")
        if isinstance(revision, bool) or not isinstance(revision, int) or revision < 0:
            raise MemoryStoreError("Canonical memory revision is invalid")
        records = document.get("validated_memory")
        if not isinstance(records, list):
            raise MemoryStoreError("Canonical memory records are invalid")
        return revision, tuple(record for record in records if isinstance(record, Mapping))

    def revision(self) -> int:
        return self.store.revision()

    @staticmethod
    def allowed(memory: Mapping[str, Any], scope: RouteScope, history_mode: str, *, include_global: bool) -> bool:
        memory_scope, _, memory_project_id = infer_memory_scope(dict(memory))
        if memory_scope == "global":
            return include_global and scope.include_global
        return memory_scope == "project" and memory_project_id in scope.project_ids and lifecycle_allowed(
            str(memory.get("status", "active")), history_mode
        )

    @staticmethod
    def _matches(memory: Mapping[str, Any], query: RetrievalQuery) -> tuple[bool, float, str]:
        memory_id = str(memory.get("memory_id", ""))
        content = str(memory.get("content", ""))
        haystack = f"{memory_id}\n{content}".casefold()
        terms = tuple(term.casefold() for term in query.terms)
        if query.strategy == "DIRECT_ID":
            return (memory_id.casefold() in terms, 1.0, "direct_id")
        if query.strategy == "RECENT_CONTINUITY":
            return (memory.get("type") in {"open_loop", "decision"}, 0.65, "continuity_type")
        if not terms:
            return (False, 0.0, "")
        matched = tuple(term for term in terms if term in haystack)
        if not matched:
            return (False, 0.0, "")
        ratio = len(matched) / len(terms)
        bases = {"EXACT_ENTITY": 0.82, "ARTIFACT": 0.78, "CONCEPT": 0.50, "DOMAIN": 0.45}
        signal = {
            "EXACT_ENTITY": "entity_match",
            "ARTIFACT": "artifact_match",
            "CONCEPT": "concept_match",
            "DOMAIN": "domain_match",
        }.get(query.strategy, "lexical_match")
        return (True, min(0.99, bases.get(query.strategy, 0.4) + ratio * 0.18), signal)

    def retrieve(
        self,
        snapshot: Iterable[Mapping[str, Any]],
        revision: int,
        query: RetrievalQuery,
        scope: RouteScope,
        history_mode: str,
        *,
        include_global: bool,
    ) -> list[RawCandidate]:
        candidates: list[RawCandidate] = []
        for memory in snapshot:
            if not self.allowed(memory, scope, history_mode, include_global=include_global):
                continue
            if not lifecycle_allowed(str(memory.get("status", "active")), history_mode):
                continue
            if query.memory_types and memory.get("type") not in query.memory_types:
                continue
            matched, score, signal = self._matches(memory, query)
            if not matched:
                continue
            memory_scope, _, project_id = infer_memory_scope(dict(memory))
            candidates.append(
                RawCandidate(
                    candidate_id=str(memory["memory_id"]),
                    source_type="memory",
                    project_id=project_id if memory_scope == "project" else None,
                    content_type=str(memory.get("type", "unknown")),
                    lifecycle=str(memory.get("status", "active")),
                    source_revision=revision,
                    canonical_ref={"authority": "memory", "memory_id": str(memory["memory_id"])},
                    query_id=query.query_id,
                    signal=signal,
                    score=score,
                )
            )
        return candidates

    def by_id(self, snapshot: Iterable[Mapping[str, Any]]) -> dict[str, Mapping[str, Any]]:
        return {str(memory.get("memory_id")): memory for memory in snapshot if memory.get("memory_id")}


class StateAdapter:
    """Expose structured current-state records as non-memory candidates."""

    def __init__(self, vault_path: str | Path):
        self.resolver = StateResolver(vault_path)
        self.registry = ProjectRegistry(vault_path)

    def resolve_projects(self, scope: RouteScope) -> dict[str, CurrentProjectState]:
        """Read every in-scope state from its canonical authority.

        The Phase 16 snapshot carried by TaskStateContext is input evidence,
        not a replacement for an authoritative read at route start.
        """
        states: dict[str, CurrentProjectState] = {}
        for project_id in scope.project_ids:
            states[project_id] = self.resolver.resolve(project_id)
        return states

    def project_status(self, project_id: str) -> Optional[str]:
        record = self.registry.get(project_id)
        return None if record is None else record.get("status")

    @staticmethod
    def unavailable_reason(state: CurrentProjectState, *, allow_archived_history: bool) -> Optional[str]:
        if state.status in {STATE_CORRUPT, STATE_UNAVAILABLE}:
            return f"state_{state.status.casefold()}"
        if state.status == PROJECT_UNKNOWN:
            return "state_project_unknown"
        if state.status == PROJECT_ARCHIVED and not allow_archived_history:
            return "state_project_archived"
        return None

    @staticmethod
    def degraded_reason(state: CurrentProjectState) -> Optional[str]:
        if state.status == STATE_NOT_FOUND:
            return "state_not_found"
        if state.freshness.get("status") == "stale_candidate":
            return "state_stale_candidate"
        return None

    @staticmethod
    def _candidate(project_id: str, revision: int, kind: str, item: Mapping[str, Any], query_id: str, score: float) -> RawCandidate:
        item_id = str(item.get("id") or kind)
        return RawCandidate(
            candidate_id=f"state:{project_id}:{revision}:{kind}:{item_id}",
            source_type="state",
            project_id=project_id,
            content_type=kind,
            lifecycle=str(item.get("status", "active")).casefold(),
            source_revision=revision,
            canonical_ref={
                "authority": "state",
                "project_id": project_id,
                "state_revision": revision,
                "kind": kind,
                "item_id": item_id,
            },
            query_id=query_id,
            signal=f"state_{kind}",
            score=score,
        )

    def retrieve(self, states: Mapping[str, CurrentProjectState], query: RetrievalQuery) -> list[RawCandidate]:
        result: list[RawCandidate] = []
        for project_id, state in sorted(states.items()):
            if state.status not in {STATE_AVAILABLE, PROJECT_ARCHIVED} or state.state_revision is None:
                continue
            revision = state.state_revision
            current = state.current
            objective = current.get("objective")
            milestone = current.get("milestone")
            if objective:
                result.append(self._candidate(project_id, revision, "objective", objective, query.query_id, 0.93))
            if milestone:
                result.append(self._candidate(project_id, revision, "milestone", milestone, query.query_id, 0.88))
            for kind, records, score in (
                ("blocker", state.active_blockers, 0.98),
                ("requirement", state.active_requirements, 0.92),
                ("work_item", state.active_work_items, 0.84),
                ("constraint", state.constraints, 0.90),
                ("risk", state.risks, 0.80),
            ):
                for item in records:
                    result.append(self._candidate(project_id, revision, kind, item, query.query_id, score))
        return result


class GraphAdapter:
    """Expand canonical memory candidates from a fresh derived graph only."""

    def __init__(self, vault_path: str | Path):
        self.vault_path = Path(vault_path)

    def expand(
        self,
        query: RetrievalQuery,
        scope: RouteScope,
        memory_revision: int,
        *,
        max_hops: int,
    ) -> tuple[set[str], Optional[str]]:
        try:
            graph = KnowledgeGraph(str(self.vault_path))
            health = graph.projection_status(memory_revision)
        except Exception:
            return set(), "graph_unavailable"
        if health.get("status") != "fresh":
            return set(), "graph_source_revision_mismatch"
        memory_ids: set[str] = set()
        try:
            for project_id in scope.project_ids or (None,):
                for term in query.terms:
                    nodes = graph.find_entities(
                        name_contains=term,
                        project_id=project_id,
                        retrieval_scope="default" if project_id else "global",
                    )
                    for node in nodes:
                        traversal = graph.traverse(
                            node["id"],
                            max_depth=max_hops,
                            project_id=project_id,
                            retrieval_scope="default" if project_id else "global",
                        )
                        for related in traversal.get("nodes", []):
                            if related.get("entity_kind") == "memory":
                                memory_ids.add(str(related["id"]))
        except Exception:
            return set(), "graph_unavailable"
        return memory_ids, None
