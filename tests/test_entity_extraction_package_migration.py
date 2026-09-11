"""IG-07 Slice 2B B2.2 package/legacy extraction parity tests."""

from __future__ import annotations

import ast
import json
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


def _memory(memory_id: str, content: str, **overrides):
    value = {
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
    value.update(overrides)
    return value


def _write_store(vault: Path, memories, revision: int = 0) -> None:
    path = vault / ".claude" / "validated-memory.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "revision": revision,
                "validated_memory": list(memories),
            }
        ),
        encoding="utf-8",
    )


def _stable(value):
    if isinstance(value, dict):
        return {
            key: _stable(item)
            for key, item in value.items()
            if key not in {"created_at", "generated_at"}
        }
    if isinstance(value, list):
        return [_stable(item) for item in value]
    return value


def test_legacy_entity_script_is_adapter_only() -> None:
    script = ROOT / "scripts" / "entity_extractor.py"
    source = script.read_text(encoding="utf-8")
    tree = ast.parse(source)
    functions = {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }

    assert functions == {"_load_canonical"}
    assert not any(isinstance(node, ast.ClassDef) for node in ast.walk(tree))
    assert "brain_eleven.extraction.entities" in source
    assert "scripts.logging_config" not in source

    canonical = (ROOT / "brain_eleven" / "extraction" / "entities.py").read_text(
        encoding="utf-8"
    )
    assert "from scripts." not in canonical


def test_package_and_adapter_rebuild_have_matching_projection_output(tmp_path: Path) -> None:
    from brain_eleven.extraction.entities import EntityExtractor as PackageExtractor
    from scripts.entity_extractor import EntityExtractor as AdapterExtractor

    package_vault = tmp_path / "package"
    adapter_vault = tmp_path / "adapter"
    memories = [_memory("m1", "Use Redis during Phase 7", project="PromtGen", project_id="p1", scope="project")]
    _write_store(package_vault, memories)
    _write_store(adapter_vault, memories)

    PackageExtractor(str(package_vault)).build_graph()
    AdapterExtractor(str(adapter_vault)).build_graph()

    package_document = json.loads(
        (package_vault / ".claude" / "knowledge-graph.json").read_text(encoding="utf-8")
    )
    adapter_document = json.loads(
        (adapter_vault / ".claude" / "knowledge-graph.json").read_text(encoding="utf-8")
    )
    assert _stable(package_document) == _stable(adapter_document)


def test_extraction_keeps_technology_and_phase_relationships_deduplicated(tmp_path: Path) -> None:
    from brain_eleven.extraction import EntityExtractor
    from brain_eleven.graph import KnowledgeGraph

    vault = tmp_path / "vault"
    graph = KnowledgeGraph(str(vault))
    extractor = EntityExtractor(str(vault))
    memory = _memory("m1", "Use Redis during Phase 7")

    extractor.extract_from_memory(memory, graph)
    extractor.extract_from_memory(memory, graph)

    mentions = graph.get_relationships("m1", direction="out", rel_type="MENTIONS")
    phases = graph.get_relationships("m1", direction="out", rel_type="RELATES_TO")
    assert len(mentions) == 1
    assert len(phases) == 1
    assert graph.get_entity(mentions[0]["target"])["name"] == "Redis"
    assert graph.get_entity(phases[0]["target"])["name"] == "Phase 7"


def test_build_graph_filters_ineligible_memories(tmp_path: Path) -> None:
    from brain_eleven.extraction import EntityExtractor

    vault = tmp_path / "vault"
    _write_store(
        vault,
        [
            _memory("active", "Keep Redis", is_approved=True),
            _memory("unapproved", "Do not publish", is_approved=False),
            _memory("superseded", "Old decision", status="superseded"),
        ],
    )

    graph = EntityExtractor(str(vault)).build_graph(save=False)

    assert graph.get_entity("active") is not None
    assert graph.get_entity("unapproved") is None
    assert graph.get_entity("superseded") is None


def test_build_graph_rejects_stale_canonical_revision(tmp_path: Path, monkeypatch) -> None:
    from brain_eleven.extraction import EntityExtractor
    from brain_eleven.graph import KnowledgeGraphProjectionStale

    vault = tmp_path / "vault"
    _write_store(vault, [_memory("m1", "Use Redis")], revision=4)
    extractor = EntityExtractor(str(vault))
    monkeypatch.setattr(extractor.store, "revision", lambda: 5)

    with pytest.raises(KnowledgeGraphProjectionStale):
        extractor.build_graph(save=False)


def test_project_graph_visibility_remains_isolated(tmp_path: Path) -> None:
    from brain_eleven.extraction import EntityExtractor

    vault = tmp_path / "vault"
    _write_store(
        vault,
        [
            _memory("global", "Global Redis guidance", scope="global"),
            _memory("project-a", "Project A uses Docker", scope="project", project="A", project_id="a"),
            _memory("project-b", "Project B uses Docker", scope="project", project="B", project_id="b"),
        ],
    )
    graph = EntityExtractor(str(vault)).build_graph(save=False)

    assert {
        item["id"]
        for item in graph.find_entities(project_id="a", entity_type="DECISION")
    } == {
        "global",
        "project-a",
    }
    assert {
        item["id"]
        for item in graph.find_entities(project_id="b", entity_type="DECISION")
    } == {
        "global",
        "project-b",
    }


def test_legacy_entity_cli_delegates_without_visible_window(tmp_path: Path) -> None:
    _write_store(tmp_path, [])
    script = ROOT / "scripts" / "entity_extractor.py"
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    completed = subprocess.run(
        [sys.executable, str(script), "--vault", str(tmp_path)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        creationflags=creationflags,
        check=False,
    )

    assert completed.returncode == 0
    assert '"total_entities"' in completed.stdout
