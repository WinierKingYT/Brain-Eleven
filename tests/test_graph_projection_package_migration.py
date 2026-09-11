"""IG-07 Slice 2B B2.1 package/legacy graph projection contract tests."""

from __future__ import annotations

import ast
import importlib
import json
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


def _write_revisioned_memory(vault: Path, revision: int = 0) -> None:
    claude_dir = vault / ".claude"
    claude_dir.mkdir(parents=True, exist_ok=True)
    (claude_dir / "validated-memory.json").write_text(
        json.dumps({"schema_version": 2, "revision": revision, "validated_memory": []}),
        encoding="utf-8",
    )


def _stable_document(value):
    if isinstance(value, dict):
        return {
            key: _stable_document(item)
            for key, item in value.items()
            if key not in {"generated_at", "created_at"}
        }
    if isinstance(value, list):
        return [_stable_document(item) for item in value]
    return value


def test_package_adapter_and_bare_graph_objects_preserve_identity() -> None:
    package = importlib.import_module("brain_eleven.graph")
    projection = importlib.import_module("brain_eleven.graph.projection")
    adapter = importlib.import_module("scripts.knowledge_graph")
    bare = importlib.import_module("knowledge_graph")

    for name in (
        "KnowledgeGraph",
        "KnowledgeGraphProjectionError",
        "KnowledgeGraphProjectionStale",
    ):
        expected = getattr(package, name)
        assert getattr(projection, name) is expected
        assert getattr(adapter, name) is expected
        assert getattr(bare, name) is expected
    assert adapter.KNOWLEDGE_GRAPH_SCHEMA_VERSION == package.KNOWLEDGE_GRAPH_SCHEMA_VERSION
    assert adapter._utc_now is projection._utc_now


def test_legacy_graph_script_is_an_adapter_only() -> None:
    script = ROOT / "scripts" / "knowledge_graph.py"
    source = script.read_text(encoding="utf-8")
    tree = ast.parse(source)

    function_names = {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    assert function_names == {"_load_canonical"}
    assert not any(isinstance(node, ast.ClassDef) for node in ast.walk(tree))
    assert "brain_eleven.graph.projection" in source
    assert "class KnowledgeGraph" not in source
    assert "scripts.logging_config" not in source

    canonical_source = (ROOT / "brain_eleven" / "graph" / "projection.py").read_text(
        encoding="utf-8"
    )
    assert "from scripts.knowledge_graph" not in canonical_source
    assert "scripts.logging_config" not in canonical_source


def test_package_and_adapter_envelope_round_trip_and_backup_parity(tmp_path: Path) -> None:
    package = importlib.import_module("brain_eleven.graph.projection")
    adapter = importlib.import_module("scripts.knowledge_graph")
    package_vault = tmp_path / "package"
    adapter_vault = tmp_path / "adapter"
    package_vault.mkdir()
    adapter_vault.mkdir()
    _write_revisioned_memory(package_vault)
    _write_revisioned_memory(adapter_vault)

    package_graph = package.KnowledgeGraph(str(package_vault))
    adapter_graph = adapter.KnowledgeGraph(str(adapter_vault))
    for graph in (package_graph, adapter_graph):
        graph.add_entity("memory", "DECISION", "Use Redis", scope="global")
        graph.add_entity("technology", "TECHNOLOGY", "Redis", entity_kind="technology")
        graph.add_relationship("memory", "MENTIONS", "technology", source_memory="memory")
        graph.mark_projection(0)
        graph.save(source_memory_revision=0)

    package_document = json.loads(
        (package_vault / ".claude" / "knowledge-graph.json").read_text(encoding="utf-8")
    )
    adapter_document = json.loads(
        (adapter_vault / ".claude" / "knowledge-graph.json").read_text(encoding="utf-8")
    )
    assert _stable_document(package_document) == _stable_document(adapter_document)
    assert package_document["schema_version"] == 2
    assert package_document["projection"] == "knowledge_graph"
    assert package_document["source_memory_revision"] == 0

    package_graph.add_entity("extra", "LESSON", "Keep the graph derived")
    adapter_graph.add_entity("extra", "LESSON", "Keep the graph derived")
    package_graph.save(source_memory_revision=0)
    adapter_graph.save(source_memory_revision=0)
    for vault in (package_vault, adapter_vault):
        backup = json.loads(
            (vault / ".claude" / "knowledge-graph.backup.json").read_text(encoding="utf-8")
        )
        assert "extra" not in backup["data"]["nodes"]


@pytest.mark.parametrize("filename,contents,expected", [
    ("missing", None, "missing"),
    (
        "legacy",
        {"directed": True, "multigraph": True, "graph": {}, "nodes": [], "edges": []},
        "legacy",
    ),
    ("malformed", "{not valid json", "corrupt"),
    (
        "invalid-envelope",
        {
            "schema_version": 2,
            "projection": "knowledge_graph",
            "source_memory_revision": -1,
            "data": {},
        },
        "corrupt",
    ),
])
def test_package_projection_preserves_missing_legacy_and_corrupt_states(
    tmp_path: Path, filename, contents, expected
) -> None:
    projection = importlib.import_module("brain_eleven.graph.projection")
    vault = tmp_path / filename
    vault.mkdir()
    graph_path = vault / ".claude" / "knowledge-graph.json"
    if contents is not None:
        graph_path.parent.mkdir()
        graph_path.write_text(
            contents if isinstance(contents, str) else json.dumps(contents),
            encoding="utf-8",
        )

    graph = projection.KnowledgeGraph(str(vault))
    assert graph.projection_status()["status"] == expected


def test_projection_status_maps_memory_store_error_to_source_unavailable(tmp_path, monkeypatch) -> None:
    projection = importlib.import_module("brain_eleven.graph.projection")
    vault = tmp_path / "vault"
    vault.mkdir()
    graph = projection.KnowledgeGraph(str(vault))
    graph.mark_projection(0)

    class FailingMemoryStore:
        def __init__(self, _vault):
            pass

        def revision(self):
            raise projection.MemoryStoreError("simulated source failure")

    monkeypatch.setattr(projection, "MemoryStore", FailingMemoryStore)
    status = graph.projection_status()
    assert status["status"] == "source_unavailable"
    assert "simulated source failure" in status["error"]


def test_package_graph_scope_visibility_remains_isolated(tmp_path: Path) -> None:
    projection = importlib.import_module("brain_eleven.graph.projection")
    graph = projection.KnowledgeGraph(str(tmp_path))
    graph.add_entity("global", "DECISION", "Global decision", scope="global")
    graph.add_entity(
        "project-a",
        "DECISION",
        "Project A decision",
        scope="project",
        project_id="a",
    )
    graph.add_entity(
        "project-b",
        "DECISION",
        "Project B decision",
        scope="project",
        project_id="b",
    )

    assert {item["id"] for item in graph.find_entities(project_id="a")} == {
        "global",
        "project-a",
    }
    assert {item["id"] for item in graph.find_entities(project_id="b")} == {
        "global",
        "project-b",
    }
    assert graph.find_entities(project_id="a", retrieval_scope="project")[0]["id"] == "project-a"


def test_legacy_demonstration_cli_still_executes_without_visible_window(tmp_path: Path) -> None:
    _write_revisioned_memory(tmp_path)
    script = ROOT / "scripts" / "knowledge_graph.py"
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    completed = subprocess.run(
        [sys.executable, str(script)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        creationflags=creationflags,
        check=False,
    )

    assert completed.returncode == 0
    assert '"total_entities"' in completed.stdout
    assert (tmp_path / ".claude" / "knowledge-graph.json").exists()
