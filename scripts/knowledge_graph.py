#!/usr/bin/env python3
"""
Brain-Eleven v3 - Knowledge Graph (Phase 11A)

Lightweight, dependency-light alternative to the Neo4j design originally
sketched in PHASE11-KICKSTART.md. Neo4j means standing up a whole extra
database service (nothing currently runs it here); networkx gives the same
entity/relationship graph model as an in-process, JSON-persisted structure
with zero new infrastructure. If a real Neo4j deployment shows up later,
this class's public interface (add_entity/add_relationship/query/traverse)
is the seam to swap the backend behind.

Persistence: a revisioned envelope containing node-link data at
.claude/knowledge-graph.json, using the same temp-write-then-rename pattern
used elsewhere in this repo (see DiskCache in cache_manager.py) to avoid
truncated files on crash.
"""

import json
import os
import shutil
import tempfile
from pathlib import Path
from datetime import datetime, timezone
from typing import List, Dict, Optional, Any

import networkx as nx

from logging_config import setup_logging
from memory_scope import infer_memory_scope
from memory_store import MemoryStore, MemoryStoreError

logger = setup_logging(__name__)


KNOWLEDGE_GRAPH_SCHEMA_VERSION = 2


class KnowledgeGraphProjectionError(RuntimeError):
    """Base class for derived knowledge-graph projection failures."""


class KnowledgeGraphProjectionStale(KnowledgeGraphProjectionError):
    """Raised when the canonical memory store changes during a rebuild."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class KnowledgeGraph:
    """Directed multigraph of entities and typed relationships between them."""

    def __init__(self, vault_path: str = "."):
        self.vault_path = Path(vault_path)
        self.graph_file = self.vault_path / ".claude" / "knowledge-graph.json"
        self.backup_file = self.vault_path / ".claude" / "knowledge-graph.backup.json"
        self.graph = nx.MultiDiGraph()
        self.source_memory_revision: Optional[int] = None
        self.projection_schema_version: Optional[int] = None
        self.generated_at: Optional[str] = None
        self._projection_state = "missing"
        self._projection_error: Optional[str] = None
        self._load()

    # -- persistence ----------------------------------------------------

    def _load(self) -> None:
        if not self.graph_file.exists():
            return
        try:
            with open(self.graph_file, encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict) and "data" in data and "projection" in data:
                if data.get("schema_version") != KNOWLEDGE_GRAPH_SCHEMA_VERSION:
                    raise ValueError(
                        f"Unsupported knowledge graph schema version: {data.get('schema_version')}"
                    )
                if data.get("projection") != "knowledge_graph":
                    raise ValueError("Unexpected knowledge graph projection name")
                source_revision = data.get("source_memory_revision")
                if not isinstance(source_revision, int) or source_revision < 0:
                    raise ValueError("Knowledge graph source revision must be a non-negative integer")
                graph_data = data["data"]
                if not isinstance(graph_data, dict):
                    raise ValueError("Knowledge graph data must be an object")
                self.graph = nx.node_link_graph(
                    graph_data, edges="edges", directed=True, multigraph=True
                )
                self.source_memory_revision = source_revision
                self.projection_schema_version = data["schema_version"]
                self.generated_at = data.get("generated_at")
                self._projection_state = "loaded"
                self._refresh_projection_state()
                return

            # Pre-revision files were plain node-link documents. Keep a
            # compatibility reader so upgrade is recoverable, but mark the
            # result explicitly: it has no trustworthy source revision.
            self.graph = nx.node_link_graph(data, edges="edges", directed=True, multigraph=True)
            self._projection_state = "legacy"
        except (json.JSONDecodeError, OSError, KeyError, TypeError, ValueError, nx.NetworkXError) as e:
            self._projection_error = str(e)
            self._projection_state = "corrupt"
            logger.warning(f"Could not load knowledge graph; projection is corrupt: {e}")
            self.graph = nx.MultiDiGraph()

    def _refresh_projection_state(self, current_revision: Optional[int] = None) -> None:
        if self.source_memory_revision is None:
            return
        try:
            current_revision = (
                MemoryStore(self.vault_path).revision()
                if current_revision is None
                else current_revision
            )
        except MemoryStoreError as exc:
            self._projection_state = "source_unavailable"
            self._projection_error = str(exc)
            return
        self._projection_state = (
            "fresh" if self.source_memory_revision == current_revision else "stale"
        )

    def projection_status(self, current_revision: Optional[int] = None) -> Dict[str, Any]:
        """Return explicit health metadata for this derived projection."""
        if self._projection_state in {"loaded", "fresh", "stale"}:
            self._refresh_projection_state(current_revision)
        return {
            "status": self._projection_state,
            "schema_version": self.projection_schema_version,
            "source_memory_revision": self.source_memory_revision,
            "generated_at": self.generated_at,
            "error": self._projection_error,
        }

    def is_current(self, current_revision: Optional[int] = None) -> bool:
        return self.projection_status(current_revision).get("status") == "fresh"

    def mark_projection(self, source_memory_revision: int) -> None:
        """Mark an in-memory rebuild as representing a canonical revision."""
        if not isinstance(source_memory_revision, int) or source_memory_revision < 0:
            raise ValueError("source_memory_revision must be a non-negative integer")
        self.source_memory_revision = source_memory_revision
        self.projection_schema_version = KNOWLEDGE_GRAPH_SCHEMA_VERSION
        self.generated_at = _utc_now()
        self._projection_error = None
        self._projection_state = "fresh"

    def save(self, source_memory_revision: Optional[int] = None) -> None:
        """Persist the graph with the canonical revision it projects."""
        if source_memory_revision is None:
            source_memory_revision = MemoryStore(self.vault_path).revision()
        if not isinstance(source_memory_revision, int) or source_memory_revision < 0:
            raise ValueError("source_memory_revision must be a non-negative integer")

        self.graph_file.parent.mkdir(parents=True, exist_ok=True)
        generated_at = _utc_now()
        envelope = {
            "schema_version": KNOWLEDGE_GRAPH_SCHEMA_VERSION,
            "projection": "knowledge_graph",
            "source_memory_revision": source_memory_revision,
            "generated_at": generated_at,
            "data": nx.node_link_data(self.graph, edges="edges"),
        }
        if self.graph_file.exists():
            shutil.copy2(self.graph_file, self.backup_file)

        descriptor, temporary_name = tempfile.mkstemp(
            prefix=".knowledge-graph-", suffix=".json", dir=self.graph_file.parent
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(envelope, handle, ensure_ascii=False, indent=2)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            Path(temporary_name).replace(self.graph_file)
        finally:
            temporary = Path(temporary_name)
            if temporary.exists():
                temporary.unlink()

        self.source_memory_revision = source_memory_revision
        self.projection_schema_version = KNOWLEDGE_GRAPH_SCHEMA_VERSION
        self.generated_at = generated_at
        self._projection_error = None
        self._projection_state = "fresh"

    def clear(self) -> None:
        self.graph = nx.MultiDiGraph()
        self.source_memory_revision = None
        self.projection_schema_version = None
        self.generated_at = None
        self._projection_error = None
        self._projection_state = "dirty"

    # -- mutation ---------------------------------------------------------

    def add_entity(self, entity_id: str, entity_type: str, name: str, **properties) -> None:
        """Add or update an entity node. Re-adding merges properties."""
        self._projection_state = "dirty"
        if self.graph.has_node(entity_id):
            self.graph.nodes[entity_id].update(properties)
            self.graph.nodes[entity_id]["name"] = name
            self.graph.nodes[entity_id]["type"] = entity_type
        else:
            self.graph.add_node(
                entity_id, type=entity_type, name=name,
                created_at=datetime.now().isoformat(), **properties,
            )

    def add_relationship(
        self, source_id: str, rel_type: str, target_id: str, **properties
    ) -> None:
        """Add a typed edge. Both entities must already exist."""
        if not self.graph.has_node(source_id) or not self.graph.has_node(target_id):
            raise ValueError(f"Both entities must exist before linking: {source_id} -> {target_id}")

        self._projection_state = "dirty"

        # Avoid piling up exact-duplicate edges (same type, same source memory).
        # NOTE: in a MultiDiGraph, out_edges(keys=True) yields (u, v, key, data)
        # where `key` is an auto-incrementing edge index, NOT the target node -
        # must compare against `v` here, not `key`.
        for _, v, _key, data in self.graph.out_edges(source_id, keys=True, data=True):
            if v == target_id and data.get("rel_type") == rel_type \
                    and data.get("source_memory") == properties.get("source_memory"):
                return

        self.graph.add_edge(
            source_id, target_id, rel_type=rel_type,
            created_at=datetime.now().isoformat(), **properties,
        )

    # -- queries ----------------------------------------------------------

    def get_entity(self, entity_id: str) -> Optional[Dict]:
        if not self.graph.has_node(entity_id):
            return None
        return {"id": entity_id, **self.graph.nodes[entity_id]}

    def is_entity_visible(self, entity_id: str, project_id: Optional[str], retrieval_scope: str) -> bool:
        """Check whether a graph node is visible under a retrieval policy."""
        return self.graph.has_node(entity_id) and self._node_allowed(entity_id, project_id, retrieval_scope)

    def find_entities(
        self,
        entity_type: Optional[str] = None,
        name_contains: Optional[str] = None,
        project_id: Optional[str] = None,
        retrieval_scope: str = "default",
    ) -> List[Dict]:
        results = []
        for node_id, data in self.graph.nodes(data=True):
            if not self._node_allowed(node_id, project_id, retrieval_scope):
                continue
            if entity_type and data.get("type") != entity_type:
                continue
            if name_contains and name_contains.lower() not in data.get("name", "").lower():
                continue
            results.append({"id": node_id, **data})
        return results

    def get_relationships(
        self,
        entity_id: str,
        direction: str = "both",
        rel_type: Optional[str] = None,
        project_id: Optional[str] = None,
        retrieval_scope: str = "default",
    ) -> List[Dict]:
        """direction: 'out' (entity_id -> X), 'in' (X -> entity_id), or 'both'."""
        if not self.graph.has_node(entity_id):
            return []

        edges = []
        def allowed(node_id):
            return self._node_allowed(node_id, project_id, retrieval_scope)

        if direction in ("out", "both"):
            for u, v, data in self.graph.out_edges(entity_id, data=True):
                if not allowed(u) or not allowed(v):
                    continue
                if rel_type is None or data.get("rel_type") == rel_type:
                    edges.append({"source": u, "target": v, **data})
        if direction in ("in", "both"):
            for u, v, data in self.graph.in_edges(entity_id, data=True):
                if not allowed(u) or not allowed(v):
                    continue
                if rel_type is None or data.get("rel_type") == rel_type:
                    edges.append({"source": u, "target": v, **data})
        return edges

    def _node_allowed(self, node_id: str, project_id: Optional[str], retrieval_scope: str) -> bool:
        if retrieval_scope == "all":
            return True
        data = self.graph.nodes.get(node_id, {})
        node_type = data.get("type", "")
        if node_type == "PROJECT":
            return (
                retrieval_scope in {"default", "project"}
                and bool(project_id)
                and data.get("project_id") == project_id
            )
        if node_type in {"DECISION", "LESSON", "OPEN_LOOP", "OBSERVATION"}:
            scope, _, memory_project_id = infer_memory_scope(data)
            if retrieval_scope == "global":
                return scope == "global"
            if retrieval_scope == "project":
                return scope == "project" and memory_project_id == project_id
            return scope == "global" or (
                scope == "project" and project_id and memory_project_id == project_id
            )
        return True

    def traverse(
        self,
        entity_id: str,
        max_depth: int = 2,
        project_id: Optional[str] = None,
        retrieval_scope: str = "default",
    ) -> Dict[str, Any]:
        """BFS out to max_depth hops (either direction). Returns a subgraph view."""
        if not self.graph.has_node(entity_id):
            return {"nodes": [], "edges": []}
        if not self._node_allowed(entity_id, project_id, retrieval_scope):
            return {"nodes": [], "edges": []}

        undirected = self.graph.to_undirected(as_view=True)
        visited = {entity_id: 0}
        frontier = [entity_id]

        while frontier:
            next_frontier = []
            for node in frontier:
                if visited[node] >= max_depth:
                    continue
                for neighbor in undirected.neighbors(node):
                    if not self._node_allowed(neighbor, project_id, retrieval_scope):
                        continue
                    if neighbor not in visited:
                        visited[neighbor] = visited[node] + 1
                        next_frontier.append(neighbor)
            frontier = next_frontier

        node_ids = set(visited.keys())
        nodes = [{"id": n, "depth": visited[n], **self.graph.nodes[n]} for n in node_ids]
        edges = [
            {"source": u, "target": v, **data}
            for u, v, data in self.graph.edges(data=True)
            if u in node_ids and v in node_ids
            and self._node_allowed(u, project_id, retrieval_scope)
            and self._node_allowed(v, project_id, retrieval_scope)
        ]
        return {"nodes": nodes, "edges": edges}

    def find_path(self, source_id: str, target_id: str) -> Optional[List[str]]:
        """Shortest path (undirected) between two entities, or None if unreachable."""
        if not (self.graph.has_node(source_id) and self.graph.has_node(target_id)):
            return None
        try:
            return nx.shortest_path(self.graph.to_undirected(as_view=True), source_id, target_id)
        except nx.NetworkXNoPath:
            return None

    def stats(self) -> Dict:
        by_type = {}
        for _, data in self.graph.nodes(data=True):
            by_type[data.get("type", "unknown")] = by_type.get(data.get("type", "unknown"), 0) + 1

        by_rel_type = {}
        for _, _, data in self.graph.edges(data=True):
            by_rel_type[data.get("rel_type", "unknown")] = by_rel_type.get(data.get("rel_type", "unknown"), 0) + 1

        return {
            "total_entities": self.graph.number_of_nodes(),
            "total_relationships": self.graph.number_of_edges(),
            "entities_by_type": by_type,
            "relationships_by_type": by_rel_type,
            "projection": self.projection_status(),
        }


if __name__ == "__main__":
    kg = KnowledgeGraph(vault_path=".")
    kg.add_entity("tech_fastapi", "TECHNOLOGY", "FastAPI")
    kg.add_entity("tech_redis", "TECHNOLOGY", "Redis")
    kg.add_entity("mem_1", "DECISION", "Use FastAPI for the API layer")
    kg.add_relationship("mem_1", "USES", "tech_fastapi", source_memory="mem_1")
    kg.add_relationship("mem_1", "USES", "tech_redis", source_memory="mem_1")
    kg.save()

    print(json.dumps(kg.stats(), indent=2))
    print(json.dumps(kg.traverse("mem_1", max_depth=1), indent=2, default=str))
