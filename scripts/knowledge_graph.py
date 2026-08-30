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

Persistence: node-link JSON at .claude/knowledge-graph.json, same
temp-write-then-rename pattern used elsewhere in this repo (see
DiskCache in cache_manager.py) to avoid truncated files on crash.
"""

import json
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional, Any

import networkx as nx

from logging_config import setup_logging

logger = setup_logging(__name__)


class KnowledgeGraph:
    """Directed multigraph of entities and typed relationships between them."""

    def __init__(self, vault_path: str = "."):
        self.vault_path = Path(vault_path)
        self.graph_file = self.vault_path / ".claude" / "knowledge-graph.json"
        self.graph = nx.MultiDiGraph()
        self._load()

    # -- persistence ----------------------------------------------------

    def _load(self) -> None:
        if not self.graph_file.exists():
            return
        try:
            with open(self.graph_file, encoding="utf-8") as f:
                data = json.load(f)
            self.graph = nx.node_link_graph(data, edges="edges", directed=True, multigraph=True)
        except (json.JSONDecodeError, OSError, KeyError) as e:
            logger.warning(f"Could not load knowledge graph, starting fresh: {e}")
            self.graph = nx.MultiDiGraph()

    def save(self) -> None:
        self.graph_file.parent.mkdir(parents=True, exist_ok=True)
        data = nx.node_link_data(self.graph, edges="edges")
        tmp_path = self.graph_file.with_suffix(".tmp")
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        tmp_path.replace(self.graph_file)

    def clear(self) -> None:
        self.graph = nx.MultiDiGraph()

    # -- mutation ---------------------------------------------------------

    def add_entity(self, entity_id: str, entity_type: str, name: str, **properties) -> None:
        """Add or update an entity node. Re-adding merges properties."""
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

    def find_entities(self, entity_type: Optional[str] = None, name_contains: Optional[str] = None) -> List[Dict]:
        results = []
        for node_id, data in self.graph.nodes(data=True):
            if entity_type and data.get("type") != entity_type:
                continue
            if name_contains and name_contains.lower() not in data.get("name", "").lower():
                continue
            results.append({"id": node_id, **data})
        return results

    def get_relationships(
        self, entity_id: str, direction: str = "both", rel_type: Optional[str] = None
    ) -> List[Dict]:
        """direction: 'out' (entity_id -> X), 'in' (X -> entity_id), or 'both'."""
        if not self.graph.has_node(entity_id):
            return []

        edges = []
        if direction in ("out", "both"):
            for u, v, data in self.graph.out_edges(entity_id, data=True):
                if rel_type is None or data.get("rel_type") == rel_type:
                    edges.append({"source": u, "target": v, **data})
        if direction in ("in", "both"):
            for u, v, data in self.graph.in_edges(entity_id, data=True):
                if rel_type is None or data.get("rel_type") == rel_type:
                    edges.append({"source": u, "target": v, **data})
        return edges

    def traverse(self, entity_id: str, max_depth: int = 2) -> Dict[str, Any]:
        """BFS out to max_depth hops (either direction). Returns a subgraph view."""
        if not self.graph.has_node(entity_id):
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
