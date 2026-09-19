"""Regression guards for the canonical runtime package boundary."""

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKER = ROOT / "brain_eleven" / "runtime" / "worker.py"
CONTEXT = ROOT / "brain_eleven" / "runtime" / "context.py"
EVIDENCE = ROOT / "brain_eleven" / "runtime" / "evidence.py"
STATE_RESOLVER = ROOT / "brain_eleven" / "state" / "resolver.py"
LEGACY_MEMORY_STORE = ROOT / "scripts" / "memory_store.py"
LEGACY_STATE_STORE = ROOT / "scripts" / "state_store.py"
LEGACY_PROJECT_REGISTRY = ROOT / "scripts" / "project_registry.py"


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
    assert "from brain_eleven._legacy import load_legacy_module" in evidence_source
    assert "from scripts.evidence import" not in evidence_source
    assert "from brain_eleven._legacy import load_legacy_module" in resolver_source
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


def test_canonical_memory_truth_surface_preserves_legacy_identity():
    from brain_eleven.memory.truth import MemoryTruthEngine as CanonicalMemoryTruthEngine
    from scripts.memory_truth import MemoryTruthEngine as LegacyMemoryTruthEngine

    assert CanonicalMemoryTruthEngine is LegacyMemoryTruthEngine


def test_memory_store_implementation_is_canonical_and_legacy_path_is_an_adapter():
    from brain_eleven.memory import MemoryStore as CanonicalMemoryStore
    from scripts.memory_store import MemoryStore as LegacyMemoryStore

    assert CanonicalMemoryStore is LegacyMemoryStore
    assert CanonicalMemoryStore.__module__ == "brain_eleven.memory.store"
    assert "class MemoryStore" not in LEGACY_MEMORY_STORE.read_text(encoding="utf-8")


def test_state_store_implementation_is_canonical_and_legacy_path_is_an_adapter():
    import brain_eleven.state.store as canonical_state_store
    import scripts.state_store as legacy_state_store
    import state_store as bare_state_store

    assert canonical_state_store is legacy_state_store is bare_state_store
    assert canonical_state_store.StateStore.__module__ == "brain_eleven.state.store"
    assert "class StateStore" not in LEGACY_STATE_STORE.read_text(encoding="utf-8")


def test_project_registry_implementation_is_canonical_and_legacy_path_is_an_adapter():
    import brain_eleven.projects.registry as canonical_project_registry
    import project_registry as bare_project_registry
    import scripts.project_registry as legacy_project_registry

    assert canonical_project_registry is legacy_project_registry is bare_project_registry
    assert canonical_project_registry.ProjectRegistry.__module__ == "brain_eleven.projects.registry"
    assert "class ProjectRegistry" not in LEGACY_PROJECT_REGISTRY.read_text(encoding="utf-8")


def test_runtime_capture_surfaces_preserve_legacy_object_identity():
    from brain_eleven.runtime.capture_event import (
        CaptureEventError,
        HookEvent,
        parse_hook_event,
    )
    from brain_eleven.runtime.evidence import (
        EvidenceBatch,
        EvidenceMessage,
        EvidenceStore,
        EvidenceTime,
    )
    from brain_eleven.runtime.capture_provenance import (
        TranscriptProvenanceError,
        resolve_transcript_path,
    )
    from brain_eleven.runtime.capture_queue import CaptureQueue, CaptureQueueError
    from brain_eleven.runtime.capture_safety import evaluate_capture
    from brain_eleven.runtime.extraction import DeterministicExtractor
    from brain_eleven.runtime.state_boundary import StateBoundary
    from brain_eleven.runtime.task_state_context import TaskStateComposer
    from brain_eleven.state.resolver import (
        CurrentProjectState,
        StateResolver,
    )
    from scripts.capture_event import (
        CaptureEventError as LegacyCaptureEventError,
        HookEvent as LegacyHookEvent,
        parse_hook_event as legacy_parse_hook_event,
    )
    from scripts.evidence import (
        EvidenceBatch as LegacyEvidenceBatch,
        EvidenceMessage as LegacyEvidenceMessage,
        EvidenceStore as LegacyEvidenceStore,
        EvidenceTime as LegacyEvidenceTime,
    )
    from scripts.capture_provenance import (
        TranscriptProvenanceError as LegacyTranscriptProvenanceError,
        resolve_transcript_path as legacy_resolve_transcript_path,
    )
    from scripts.capture_queue import (
        CaptureQueue as LegacyCaptureQueue,
        CaptureQueueError as LegacyCaptureQueueError,
    )
    from scripts.capture_safety import evaluate_capture as legacy_evaluate_capture
    from scripts.extraction import DeterministicExtractor as LegacyDeterministicExtractor
    from scripts.state_resolver import (
        CurrentProjectState as LegacyCurrentProjectState,
        StateResolver as LegacyStateResolver,
    )
    from scripts.state_boundary import StateBoundary as LegacyStateBoundary
    from scripts.task_state_context import TaskStateComposer as LegacyTaskStateComposer

    assert CaptureEventError is LegacyCaptureEventError
    assert HookEvent is LegacyHookEvent
    assert parse_hook_event is legacy_parse_hook_event
    assert TranscriptProvenanceError is LegacyTranscriptProvenanceError
    assert resolve_transcript_path is legacy_resolve_transcript_path
    assert CaptureQueue is LegacyCaptureQueue
    assert CaptureQueueError is LegacyCaptureQueueError
    assert evaluate_capture is legacy_evaluate_capture
    assert DeterministicExtractor is LegacyDeterministicExtractor
    assert StateBoundary is LegacyStateBoundary
    assert EvidenceBatch is LegacyEvidenceBatch
    assert EvidenceMessage is LegacyEvidenceMessage
    assert EvidenceStore is LegacyEvidenceStore
    assert EvidenceTime is LegacyEvidenceTime
    assert TaskStateComposer is LegacyTaskStateComposer
    assert CurrentProjectState is LegacyCurrentProjectState
    assert StateResolver is LegacyStateResolver
