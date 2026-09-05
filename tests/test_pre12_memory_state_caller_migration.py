from __future__ import annotations

import ast
from pathlib import Path

from brain_eleven.memory import MemoryStore as PackagedMemoryStore
from brain_eleven.state import StateService as PackagedStateService
from authority.adapters import MemoryStore as AuthorityMemoryStore
from context_router.adapters import MemoryStore as RouterMemoryStore
from evals.authority_provider import MemoryStore as AuthorityProviderMemoryStore
from evals.compiler_v2_provider import MemoryStore as CompilerProviderMemoryStore
from evals.router_provider import MemoryStore as RouterProviderMemoryStore
from evals.router_provider import StateService as RouterProviderStateService
from evals.task_state_eval import MemoryStore as TaskStateMemoryStore
from evals.task_state_eval import StateService as TaskStateService


CALLERS = (
    "context_router/adapters.py",
    "authority/adapters.py",
    "evals/router_provider.py",
    "evals/authority_provider.py",
    "evals/compiler_v2_provider.py",
    "evals/task_state_eval.py",
    "evals/authority_evaluation.py",
    "evals/compiler_v2_evaluation.py",
    "evals/compiler_v2_benchmark.py",
    "evals/router_benchmark.py",
)

STATE_MUTATION_CALLERS = (
    "scripts/state.py",
    "scripts/state_boundary.py",
    "scripts/state_resolver.py",
)

MEMORY_MUTATION_CALLERS = (
    "scripts/memory-lifecycle.py",
    "scripts/memory_truth.py",
    "scripts/memory_provenance.py",
)


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    }


def test_core_and_evaluation_callers_use_packaged_store_surfaces() -> None:
    root = Path(__file__).resolve().parents[1]
    for relative_path in CALLERS:
        imports = _imports(root / relative_path)
        assert "memory_store" not in imports, relative_path
        assert "state_store" not in imports, relative_path


def test_state_mutation_and_cli_callers_use_packaged_state_surface() -> None:
    root = Path(__file__).resolve().parents[1]
    for relative_path in STATE_MUTATION_CALLERS:
        imports = _imports(root / relative_path)
        assert "state_store" not in imports, relative_path
        assert "brain_eleven.state" in imports, relative_path


def test_state_resolver_preserves_packaged_store_identity() -> None:
    from state_resolver import MemoryStore as ResolverMemoryStore
    from state_resolver import StateStore as ResolverStateStore

    from brain_eleven.memory import MemoryStore
    from brain_eleven.state import StateStore

    assert ResolverMemoryStore is MemoryStore
    assert ResolverStateStore is StateStore


def test_memory_mutation_callers_use_packaged_memory_surface() -> None:
    root = Path(__file__).resolve().parents[1]
    for relative_path in MEMORY_MUTATION_CALLERS:
        imports = _imports(root / relative_path)
        assert "memory_store" not in imports, relative_path
        assert "brain_eleven.memory" in imports, relative_path


def test_memory_callers_preserve_canonical_object_identity() -> None:
    assert RouterMemoryStore is PackagedMemoryStore
    assert AuthorityMemoryStore is PackagedMemoryStore
    assert RouterProviderMemoryStore is PackagedMemoryStore
    assert AuthorityProviderMemoryStore is PackagedMemoryStore
    assert CompilerProviderMemoryStore is PackagedMemoryStore
    assert TaskStateMemoryStore is PackagedMemoryStore


def test_state_callers_preserve_canonical_object_identity() -> None:
    assert RouterProviderStateService is PackagedStateService
    assert TaskStateService is PackagedStateService
