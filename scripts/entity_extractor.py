#!/usr/bin/env python3
"""
Brain-Eleven v3 - Entity Extractor (Phase 11B)

Populates the knowledge graph (knowledge_graph.py) from memories in
.claude/validated-memory.json.

Deliberately NOT the spaCy + GPT-4 pipeline sketched in
PHASE11-KICKSTART.md: spaCy isn't installed here, and GPT-4 extraction
needs an OpenAI key that also isn't configured. A lexicon + regex
extractor is less flexible but fully deterministic, testable without
mocking an LLM, and costs nothing to run - consistent with how
summarizer.py and anomaly_detector.py were built in Phase 10.

Entities recognized:
- Each memory itself becomes a node (type = its memory type, e.g. DECISION)
- TECHNOLOGY: known tools/frameworks mentioned in content (lexicon match)
- PHASE: "Phase N" references (project milestones in this repo's own history)

Relationships:
- (memory)-[:USES]->(technology)      when a decision/observation names a tech
- (memory)-[:MENTIONS]->(technology)  for other memory types
- (memory)-[:RELATES_TO]->(phase)     when content references a Phase N
"""

import re
import json
from pathlib import Path
from typing import List, Dict, Tuple

from logging_config import setup_logging
from knowledge_graph import KnowledgeGraph, KnowledgeGraphProjectionStale
from memory_scope import infer_memory_scope
from memory_store import MemoryStore

logger = setup_logging(__name__)

# Canonical name -> regex patterns (word-boundary, case-insensitive) that
# should resolve to it. Extend this list as the project's stack grows.
TECH_LEXICON: Dict[str, List[str]] = {
    "FastAPI": [r"fastapi"],
    "Docker": [r"docker"],
    "Redis": [r"redis"],
    "PostgreSQL": [r"postgres(?:ql)?"],
    "Neo4j": [r"neo4j"],
    "OpenAI": [r"openai"],
    "Python": [r"python"],
    "React": [r"react"],
    "GitHub Actions": [r"github actions"],
    "pytest": [r"pytest"],
    "ULID": [r"\bulid\b"],
    "Obsidian": [r"obsidian"],
    "mem0": [r"mem0"],
    "Uvicorn": [r"uvicorn"],
    "spaCy": [r"spacy"],
    "networkx": [r"networkx"],
}

PHASE_PATTERN = re.compile(r"\bphase\s+(\d+)\b", re.IGNORECASE)


class ProjectionInvariantError(RuntimeError):
    """Raised when a graph projection cannot be proven to match the store."""


def _slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


class EntityExtractor:
    """Extracts entities/relationships from memories into a KnowledgeGraph."""

    def __init__(self, vault_path: str = "."):
        self.vault_path = Path(vault_path)
        self.memory_file = self.vault_path / ".claude" / "validated-memory.json"
        self.store = MemoryStore(self.vault_path)

    @staticmethod
    def _eligible_memories(data: Dict) -> List[Dict]:
        memories = data.get("validated_memory", [])
        return [
            m for m in memories
            if m.get("status", "active") == "active" and m.get("is_approved", False)
        ]

    def load_memories(self, data: Dict = None) -> List[Dict]:
        """
        Load memories eligible for the graph: active status AND approved.

        Excluding resolved/superseded/deleted matters here more than it
        would for a text digest - resolved/superseded content in the graph
        can surface as "current" evidence in a chat answer (e.g. "Redis"
        pointing at both a superseded decision that rejected it and a
        newer one that adopted it), silently reintroducing the memory
        poisoning problem Phase 5 was built to close, just at the graph
        layer instead of the retriever layer.
        """
        snapshot = self.store.load() if data is None else data
        return self._eligible_memories(snapshot)

    def validate_projection(
        self, graph: KnowledgeGraph, canonical: Dict = None
    ) -> Dict:
        """Check that graph memory nodes and project provenance match the store."""
        snapshot = self.store.load() if canonical is None else canonical
        eligible = {
            memory.get("memory_id"): memory
            for memory in self._eligible_memories(snapshot)
            if memory.get("memory_id")
        }
        memory_nodes = {
            node_id: data
            for node_id, data in graph.graph.nodes(data=True)
            if data.get("entity_kind") == "memory"
        }
        errors = []
        missing = sorted(set(eligible) - set(memory_nodes))
        unexpected = sorted(set(memory_nodes) - set(eligible))
        if missing:
            errors.append(f"Missing eligible memory nodes: {', '.join(missing)}")
        if unexpected:
            errors.append(f"Unexpected or ineligible memory nodes: {', '.join(unexpected)}")

        for memory_id in memory_nodes:
            memory = eligible.get(memory_id)
            if not memory:
                continue
            scope, _project_label, project_id = infer_memory_scope(memory)
            if scope != "project" or not project_id:
                continue
            belongs_to = graph.get_relationships(
                memory_id, direction="out", rel_type="BELONGS_TO", retrieval_scope="all"
            )
            matching = [
                edge for edge in belongs_to
                if graph.graph.nodes.get(edge["target"], {}).get("project_id") == project_id
            ]
            if len(matching) != 1:
                errors.append(
                    f"Project memory {memory_id} must have exactly one BELONGS_TO "
                    f"edge for project {project_id}"
                )

        projection = graph.projection_status(current_revision=int(snapshot.get("revision", 0)))
        if projection["status"] != "fresh":
            errors.append(
                f"Graph projection status is {projection['status']}, expected fresh"
            )

        return {
            "valid": not errors,
            "errors": errors,
            "canonical_revision": int(snapshot.get("revision", 0)),
            "graph_memory_nodes": len(memory_nodes),
            "eligible_memories": len(eligible),
            "projection": projection,
        }

    def assert_projection_consistent(
        self, graph: KnowledgeGraph, canonical: Dict = None
    ) -> Dict:
        report = self.validate_projection(graph, canonical=canonical)
        if not report["valid"]:
            raise ProjectionInvariantError("; ".join(report["errors"]))
        return report

    @staticmethod
    def find_technologies(content: str) -> List[str]:
        """Return canonical technology names mentioned in content."""
        found = []
        for canonical, patterns in TECH_LEXICON.items():
            if any(re.search(p, content, re.IGNORECASE) for p in patterns):
                found.append(canonical)
        return found

    @staticmethod
    def find_phase_references(content: str) -> List[int]:
        """Return distinct Phase N numbers referenced in content."""
        return sorted({int(n) for n in PHASE_PATTERN.findall(content)})

    def extract_from_memory(self, memory: Dict, graph: KnowledgeGraph) -> Tuple[int, int]:
        """
        Extract entities/relationships from one memory into the graph.
        Returns (entities_added, relationships_added) for reporting.
        """
        memory_id = memory.get("memory_id")
        content = memory.get("content", "")
        mem_type = memory.get("type", "unknown")
        scope, project_label, project_id = infer_memory_scope(memory)

        if not memory_id or not content:
            return (0, 0)

        graph.add_entity(
            memory_id, mem_type.upper(), content[:80],
            entity_kind="memory",
            confidence=memory.get("confidence"),
            status=memory.get("status"),
            scope=scope,
            project=project_label,
            project_id=project_id,
        )
        entities_added = 1
        relationships_added = 0

        if scope == "project" and project_id:
            project_entity_id = f"project_{project_id}"
            graph.add_entity(
                project_entity_id,
                "PROJECT",
                project_label or project_id,
                entity_kind="project",
                project_id=project_id,
            )
            graph.add_relationship(
                memory_id,
                "BELONGS_TO",
                project_entity_id,
                source_memory=memory_id,
            )
            entities_added += 1
            relationships_added += 1

        # Always MENTIONS, never USES/DEPENDS_ON/etc: a lexicon+regex match
        # can't tell "we adopted Redis" from "we decided against Redis" -
        # a memory of type "decision" that names a technology is not
        # evidence the decision was to use it. Stronger relationship types
        # need an extractor that actually reads the sentence (structured
        # metadata, an explicit parser, or a provenance-carrying semantic
        # step), not a keyword hit. This is an entity-mention graph, not
        # (yet) a graph of asserted facts.
        for tech in self.find_technologies(content):
            tech_id = f"tech_{_slugify(tech)}"
            graph.add_entity(tech_id, "TECHNOLOGY", tech, entity_kind="technology")
            graph.add_relationship(memory_id, "MENTIONS", tech_id, source_memory=memory_id)
            entities_added += 1
            relationships_added += 1

        for phase_num in self.find_phase_references(content):
            phase_id = f"phase_{phase_num}"
            graph.add_entity(phase_id, "PHASE", f"Phase {phase_num}", entity_kind="phase")
            graph.add_relationship(memory_id, "RELATES_TO", phase_id, source_memory=memory_id)
            entities_added += 1
            relationships_added += 1

        return (entities_added, relationships_added)

    def build_graph(self, graph: KnowledgeGraph = None, save: bool = True) -> KnowledgeGraph:
        """
        Rebuild the graph from scratch against the current canonical store.

        Always clears first: the graph is a derived projection of
        validated-memory.json, not a second source of truth accumulating
        its own state. Without this, a memory that gets deleted or moved
        out of "active" stays in the graph forever (loaded from the
        persisted knowledge-graph.json and never removed), and re-running
        this after content changes just layers new nodes on top of stale
        ones instead of reflecting the current store.
        """
        graph = graph if graph is not None else KnowledgeGraph(str(self.vault_path))
        graph.clear()
        snapshot = self.store.load()
        source_revision = int(snapshot["revision"])
        memories = self.load_memories(snapshot)

        total_entities, total_relationships = 0, 0
        for memory in memories:
            e, r = self.extract_from_memory(memory, graph)
            total_entities += e
            total_relationships += r

        logger.info(
            f"Extracted from {len(memories)} memories: "
            f"{graph.stats()['total_entities']} unique entities, "
            f"{graph.stats()['total_relationships']} relationships"
        )

        # A rebuild must not publish a projection built from an obsolete
        # snapshot. The canonical store transaction boundary guarantees the
        # revision check is meaningful even when another process writes here.
        current_revision = self.store.revision()
        if current_revision != source_revision:
            raise KnowledgeGraphProjectionStale(
                "Canonical memory store changed during graph rebuild: "
                f"started at revision {source_revision}, now {current_revision}"
            )

        graph.mark_projection(source_revision)
        self.assert_projection_consistent(graph, canonical=snapshot)

        if save:
            graph.save(source_memory_revision=source_revision)

        return graph


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Build the Brain-Eleven knowledge graph from memories")
    parser.add_argument("--vault", default=".", help="Path to vault root")
    args = parser.parse_args()

    extractor = EntityExtractor(vault_path=args.vault)
    graph = extractor.build_graph()

    print(json.dumps(graph.stats(), indent=2))
