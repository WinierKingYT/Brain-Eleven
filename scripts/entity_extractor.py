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
from knowledge_graph import KnowledgeGraph

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

# Memory types where naming a technology reads as "we built with it" rather
# than "it came up in passing".
USES_TYPES = {"decision"}


def _slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


class EntityExtractor:
    """Extracts entities/relationships from memories into a KnowledgeGraph."""

    def __init__(self, vault_path: str = "."):
        self.vault_path = Path(vault_path)
        self.memory_file = self.vault_path / ".claude" / "validated-memory.json"

    def load_memories(self) -> List[Dict]:
        if not self.memory_file.exists():
            return []
        with open(self.memory_file, encoding="utf-8") as f:
            data = json.load(f)
        return data.get("validated_memory", [])

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

        if not memory_id or not content:
            return (0, 0)

        graph.add_entity(
            memory_id, mem_type.upper(), content[:80],
            confidence=memory.get("confidence"),
            status=memory.get("status"),
        )
        entities_added = 1
        relationships_added = 0

        rel_type = "USES" if mem_type in USES_TYPES else "MENTIONS"
        for tech in self.find_technologies(content):
            tech_id = f"tech_{_slugify(tech)}"
            graph.add_entity(tech_id, "TECHNOLOGY", tech)
            graph.add_relationship(memory_id, rel_type, tech_id, source_memory=memory_id)
            entities_added += 1
            relationships_added += 1

        for phase_num in self.find_phase_references(content):
            phase_id = f"phase_{phase_num}"
            graph.add_entity(phase_id, "PHASE", f"Phase {phase_num}")
            graph.add_relationship(memory_id, "RELATES_TO", phase_id, source_memory=memory_id)
            entities_added += 1
            relationships_added += 1

        return (entities_added, relationships_added)

    def build_graph(self, graph: KnowledgeGraph = None, save: bool = True) -> KnowledgeGraph:
        """Extract from every memory and populate (or rebuild) the graph."""
        graph = graph if graph is not None else KnowledgeGraph(str(self.vault_path))
        memories = self.load_memories()

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

        if save:
            graph.save()

        return graph


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Build the Brain-Eleven knowledge graph from memories")
    parser.add_argument("--vault", default=".", help="Path to vault root")
    args = parser.parse_args()

    extractor = EntityExtractor(vault_path=args.vault)
    graph = extractor.build_graph()

    print(json.dumps(graph.stats(), indent=2))
