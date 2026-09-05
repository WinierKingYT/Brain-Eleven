from __future__ import annotations

import ast
from pathlib import Path

from brain_eleven.projects.registry import ProjectRegistry, ProjectRegistryError
from capture_event import ProjectRegistry as CaptureProjectRegistry
from capture_event import ProjectRegistryError as CaptureProjectRegistryError
from context_router.adapters import ProjectRegistry as AdapterProjectRegistry
from context_router.adapters import ProjectRegistryError as AdapterProjectRegistryError
from state_resolver import ProjectRegistry as ResolverProjectRegistry
from state_resolver import ProjectRegistryError as ResolverProjectRegistryError
from task_model import ProjectRegistry as TaskProjectRegistry
from task_model import ProjectRegistryError as TaskProjectRegistryError


def test_read_only_resolution_callers_use_the_package_boundary() -> None:
    assert CaptureProjectRegistry is ProjectRegistry
    assert AdapterProjectRegistry is ProjectRegistry
    assert ResolverProjectRegistry is ProjectRegistry
    assert TaskProjectRegistry is ProjectRegistry
    assert CaptureProjectRegistryError is ProjectRegistryError
    assert AdapterProjectRegistryError is ProjectRegistryError
    assert ResolverProjectRegistryError is ProjectRegistryError
    assert TaskProjectRegistryError is ProjectRegistryError


def test_remaining_production_callers_use_the_package_boundary() -> None:
    root = Path(__file__).resolve().parents[1]
    callers = (
        "scripts/context-compiler.py",
        "scripts/memory_backup.py",
        "scripts/memory_scope.py",
        "scripts/project-registry.py",
        "scripts/remember.py",
        "scripts/search-api.py",
        "scripts/state_boundary.py",
        "evals/authority_evaluation.py",
        "evals/compiler_v2_benchmark.py",
        "evals/compiler_v2_evaluation.py",
        "evals/router_benchmark.py",
        "evals/router_evaluation.py",
        "evals/router_provider.py",
        "evals/task_state_eval.py",
    )
    for relative_path in callers:
        tree = ast.parse((root / relative_path).read_text(encoding="utf-8"))
        imports = {
            node.module
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
        }
        assert "brain_eleven.projects.registry" in imports, relative_path


def test_legacy_registry_imports_are_limited_to_compatibility_edges() -> None:
    root = Path(__file__).resolve().parents[1]
    allowed = {
        "brain_eleven/projects/registry.py",
        "scripts/capture_event.py",
        "scripts/memory_scope.py",
        "scripts/state_store.py",
    }
    for path in (root / "scripts").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        uses_legacy_import = any(
            isinstance(node, ast.ImportFrom) and node.module == "project_registry"
            for node in ast.walk(tree)
        )
        if uses_legacy_import:
            assert path.relative_to(root).as_posix() in allowed
