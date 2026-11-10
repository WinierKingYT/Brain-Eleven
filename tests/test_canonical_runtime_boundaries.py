"""Regression guards for the canonical runtime package boundary."""

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKER = ROOT / "brain_eleven" / "runtime" / "worker.py"
CONTEXT = ROOT / "brain_eleven" / "runtime" / "context.py"
EVIDENCE = ROOT / "brain_eleven" / "runtime" / "evidence.py"
STATE_RESOLVER = ROOT / "brain_eleven" / "state" / "resolver.py"


def test_worker_uses_canonical_surfaces_for_memory_truth_and_evidence():
    source = WORKER.read_text(encoding="utf-8")

    assert "from brain_eleven.memory.truth import MemoryTruthEngine, TruthCandidate" in source
    assert "from .evidence import EvidenceStore, EvidenceBatch, read_increment" in source
    assert "from .capture_event import EVENT_USER_PROMPT_SUBMIT, parse_hook_event" in source
    assert "from .capture_provenance import TranscriptProvenanceError, resolve_transcript_path" in source
    assert "from .capture_queue import CaptureQueue" in source
    assert "from .capture_safety import evaluate_capture" in source
    assert "from .extraction import DeterministicExtractor, _segments, _classify_commitment, _memory_type" in source
    assert "from .state_boundary import StateBoundary" in source
    assert "from scripts.memory_truth import" not in source
    assert "from scripts.evidence import" not in source
    assert "from scripts.capture_event import" not in source
    assert "from scripts.capture_provenance import" not in source
    assert "from scripts.capture_queue import" not in source
    assert "from scripts.capture_safety import" not in source
    assert "from scripts.extraction import" not in source
    assert "from scripts.state_boundary import" not in source


def test_remaining_runtime_callers_use_package_boundaries():
    context_source = CONTEXT.read_text(encoding="utf-8")
    evidence_source = EVIDENCE.read_text(encoding="utf-8")
    resolver_source = STATE_RESOLVER.read_text(encoding="utf-8")

    assert "from .capture_safety import evaluate_capture" in context_source
    assert "from .task_state_context import TaskStateComposer" in context_source
    assert "from scripts.capture_safety import" not in context_source
    assert "from scripts.task_state_context import" not in context_source
    assert "load_legacy_module" not in evidence_source
    assert "from scripts.evidence import" not in evidence_source
    assert "load_legacy_module" not in resolver_source
    assert "from scripts.state_resolver import" not in resolver_source


def test_brain_eleven_package_has_no_direct_scripts_import_edges():
    for path in (ROOT / "brain_eleven").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imports = {
            node.module
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module
        }
        imports.update(
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        )
        assert not any(name == "scripts" or name.startswith("scripts.") for name in imports), path
