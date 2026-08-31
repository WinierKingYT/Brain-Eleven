"""Regression tests for revisioned and recoverable graph projections."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from entity_extractor import EntityExtractor  # noqa: E402
from knowledge_graph import KnowledgeGraph  # noqa: E402
from memory_store import MemoryStore  # noqa: E402


def make_memory(memory_id="m1", content="Chose Redis", **overrides):
    memory = {
        "memory_id": memory_id,
        "source_id": f"test:{memory_id}",
        "type": "decision",
        "content": content,
        "confidence": 0.9,
        "timestamp": "2026-08-31T12:00:00",
        "quality_score": 0.9,
        "status": "active",
        "is_approved": True,
    }
    memory.update(overrides)
    return memory


def write_store(vault, memories, revision=0):
    path = vault / ".claude" / "validated-memory.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"schema_version": 2, "revision": revision, "validated_memory": memories}),
        encoding="utf-8",
    )


@pytest.fixture
def vault(tmp_path):
    (tmp_path / ".claude").mkdir()
    return tmp_path


def test_graph_envelope_records_canonical_revision(vault):
    write_store(vault, [make_memory()])
    graph = EntityExtractor(str(vault)).build_graph()

    document = json.loads((vault / ".claude" / "knowledge-graph.json").read_text(encoding="utf-8"))

    assert document["schema_version"] == 2
    assert document["projection"] == "knowledge_graph"
    assert document["source_memory_revision"] == 0
    assert "generated_at" in document
    assert "nodes" in document["data"]
    assert graph.is_current(0)


def test_graph_reports_stale_after_canonical_revision_changes(vault):
    store = MemoryStore(vault)
    store.append(make_memory())
    EntityExtractor(str(vault)).build_graph()

    store.append(make_memory(memory_id="m2", content="Use PostgreSQL"))
    reloaded = KnowledgeGraph(str(vault))

    status = reloaded.projection_status()
    assert status["status"] == "stale"
    assert status["source_memory_revision"] == 1


def test_corrupt_graph_is_visible_and_rebuild_recovers(vault):
    write_store(vault, [make_memory()])
    graph_path = vault / ".claude" / "knowledge-graph.json"
    graph_path.write_text("{not valid json", encoding="utf-8")

    corrupt = KnowledgeGraph(str(vault))
    assert corrupt.projection_status()["status"] == "corrupt"

    rebuilt = EntityExtractor(str(vault)).build_graph()
    assert rebuilt.get_entity("m1") is not None
    assert KnowledgeGraph(str(vault)).is_current(0)


def test_projection_oracle_rejects_missing_project_provenance(vault):
    project_memory = make_memory(
        scope="project", project="Project A", project_id="project-a"
    )
    write_store(vault, [project_memory])
    extractor = EntityExtractor(str(vault))
    graph = extractor.build_graph(save=False)

    edge = next(
        (u, v, key)
        for u, v, key, data in graph.graph.out_edges("m1", keys=True, data=True)
        if data.get("rel_type") == "BELONGS_TO"
    )
    graph.graph.remove_edge(*edge)

    report = extractor.validate_projection(graph)
    assert report["valid"] is False
    assert any("BELONGS_TO" in error for error in report["errors"])
