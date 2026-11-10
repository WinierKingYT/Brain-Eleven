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

