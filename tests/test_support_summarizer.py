"""Contract and parity tests for the IG-07 summarizer migration."""

from __future__ import annotations

import ast
import importlib
import json
import subprocess
import sys
from pathlib import Path

from brain_eleven.support import (
    MemorySummarizer as PackagedMemorySummarizer,
    jaccard_similarity as PackagedJaccardSimilarity,
    tokenize as PackagedTokenize,
)
from brain_eleven.support.summarizer import MemorySummarizer, jaccard_similarity, tokenize


ROOT = Path(__file__).resolve().parents[1]


def _write_memories(vault: Path, memories: list[dict]) -> None:
    claude_dir = vault / ".claude"
    claude_dir.mkdir(exist_ok=True)
    (claude_dir / "validated-memory.json").write_text(
        json.dumps({"validated_memory": memories}),
        encoding="utf-8",
    )


def test_package_legacy_and_anomaly_helpers_share_identity() -> None:
    legacy = importlib.import_module("scripts.summarizer")
    bare_legacy = importlib.import_module("summarizer")
    anomaly = importlib.import_module("scripts.anomaly_detector")

    assert PackagedMemorySummarizer is MemorySummarizer is legacy.MemorySummarizer
    assert PackagedMemorySummarizer is bare_legacy.MemorySummarizer
    assert PackagedTokenize is tokenize is legacy.tokenize is anomaly.tokenize
    assert PackagedJaccardSimilarity is jaccard_similarity is legacy.jaccard_similarity
    assert jaccard_similarity is anomaly.jaccard_similarity


def test_legacy_summarizer_file_is_only_an_adapter() -> None:
    source_path = ROOT / "scripts" / "summarizer.py"
    source = source_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    defined_classes = {
        node.name for node in ast.walk(tree) if isinstance(node, ast.ClassDef)
    }
    defined_functions = {
        node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)
    }

    assert "brain_eleven.support.summarizer" in source
    assert not defined_classes & {"MemorySummarizer"}
    assert not defined_functions & {"tokenize", "jaccard_similarity"}
    assert "def generate_digest" not in source


def test_package_and_legacy_summarizers_produce_matching_scoped_digest(tmp_path: Path) -> None:
    _write_memories(
        tmp_path,
        [
            {
                "memory_id": "p1",
                "type": "decision",
                "content": "Use SQLite for the project database",
                "project_id": "project-one",
                "confidence": 0.9,
                "quality_score": 0.9,
                "status": "active",
                "source_id": "daily:2026-08-28:decision:0:0",
            },
            {
                "memory_id": "p2",
                "type": "decision",
                "content": "Use PostgreSQL for the other project database",
                "project_id": "project-two",
                "confidence": 0.9,
                "quality_score": 0.9,
                "status": "active",
                "source_id": "daily:2026-08-28:decision:0:1",
            },
        ],
    )
    legacy = importlib.import_module("scripts.summarizer")

    package_digest = MemorySummarizer(str(tmp_path)).generate_digest(
        project_id="project-one",
        retrieval_scope="project",
    )
    legacy_digest = legacy.MemorySummarizer(str(tmp_path)).generate_digest(
        project_id="project-one",
        retrieval_scope="project",
    )

    assert package_digest["total_memories_considered"] == 1
    assert package_digest["by_type"]["decision"][0]["memory_id"] == "p1"
    assert {
        key: value for key, value in package_digest.items() if key != "generated_at"
    } == {
        key: value for key, value in legacy_digest.items() if key != "generated_at"
    }


def test_direct_execution_preserves_json_digest_contract(tmp_path: Path) -> None:
    _write_memories(tmp_path, [])
    script = ROOT / "scripts" / "summarizer.py"
    result = subprocess.run(
        [sys.executable, str(script), "--vault", str(tmp_path), "--json"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    digest = json.loads(result.stdout)
    assert digest["total_memories_considered"] == 0
    assert digest["total_after_dedup"] == 0
