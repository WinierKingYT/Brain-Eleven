"""Gate evidence for the IG-07 Slice 2F task-state-context inversion."""

from __future__ import annotations

import ast
import copy
import importlib
import json
import os
import subprocess
import sys
from pathlib import Path

from brain_eleven.projects.registry import ProjectRegistry
from brain_eleven.state import StateService


ROOT = Path(__file__).resolve().parents[1]
CANONICAL_PATH = ROOT / "brain_eleven" / "runtime" / "task_state_context.py"
ADAPTER_PATH = ROOT / "scripts" / "task_state_context.py"

BASELINE_CALLERS = frozenset(
    {
        "authority/serialization.py",
        "authority/shadow.py",
        "brain_eleven/runtime/context.py",
        "context_compiler_v2/shadow.py",
        "context_router/__main__.py",
        "evals/authority_evaluation.py",
        "evals/authority_provider.py",
        "evals/compiler_v2_benchmark.py",
        "evals/compiler_v2_evaluation.py",
        "evals/compiler_v2_provider.py",
        "evals/router_benchmark.py",
        "evals/router_evaluation.py",
        "evals/router_provider.py",
        "evals/runtime_provider.py",
        "tests/context_engine/test_foundation_pipeline.py",
        "tests/test_authority_resolver.py",
        "tests/test_canonical_runtime_boundaries.py",
        "tests/test_context_compiler_v2.py",
        "tests/test_context_compiler_v2_hardening.py",
        "tests/test_context_engine_operational_surfaces.py",
        "tests/test_context_router.py",
        "tests/test_pre13_runtime.py",
        "tests/test_task_state_context.py",
        "tests/test_tsc01_timezone.py",
        "tests/test_tsc02_identity.py",
        "tests/test_w22_optional_omission.py",
    }
)

PUBLIC_NAMES = (
    "TASK_STATE_CONTEXT_SCHEMA_VERSION",
    "LINEAGE_STATUSES",
    "TaskStateLineageError",
    "TaskStateLineage",
    "TaskStateContext",
    "TaskStateComposer",
    "main",
)


def _task_state_import_files() -> set[str]:
    result: set[str] = set()
    source_roots = (
        ROOT / "authority",
        ROOT / "brain_eleven",
        ROOT / "context_compiler_v2",
        ROOT / "context_router",
        ROOT / "evals",
        ROOT / "scripts",
        ROOT / "tests",
    )
    for source_root in source_roots:
        for path in source_root.rglob("*.py"):
            relative = path.relative_to(ROOT).as_posix()
            if relative in {
                "scripts/task_state_context.py",
                "brain_eleven/runtime/task_state_context.py",
                "tests/test_task_state_context_package_migration.py",
            }:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=relative)
            if any(
                isinstance(node, ast.ImportFrom)
                and node.module
                and (
                    node.module == "task_state_context"
                    or node.module.endswith(".task_state_context")
                )
                for node in ast.walk(tree)
            ):
                result.add(relative)
    return result


def _strip_generated_fields(document: dict) -> dict:
    normalized = copy.deepcopy(document)
    normalized["task"].pop("task_id", None)
    normalized["task"].pop("created_at", None)
    return normalized


def _run_cli(module: str, vault: Path, project_root: Path, *, cwd: Path) -> subprocess.CompletedProcess[str]:
    command = [
        sys.executable,
        *(["-m", module] if module.startswith("brain_eleven.") else [module]),
        "--vault",
        str(vault),
        "--project-root",
        str(project_root),
        "--request",
        "Phase 17 task state planını doğrula.",
        "--json",
    ]
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    return subprocess.run(
        command,
        cwd=cwd,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )


def test_slice2f_inventory_has_exactly_the_bounded_26_caller_files() -> None:
    assert _task_state_import_files() == set(BASELINE_CALLERS)


def test_canonical_task_state_module_owns_the_implementation_and_package_edges() -> None:
    source = CANONICAL_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(CANONICAL_PATH))
    imports = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    }

    assert "brain_eleven.runtime.task" in imports
    assert "brain_eleven.state.resolver" in imports
    assert "brain_eleven.projects.identity" in imports
    assert not any(name == "scripts" or name.startswith("scripts.") for name in imports)
    assert "load_legacy_module" not in source
    for definition in ("TaskStateLineageError", "TaskStateLineage", "TaskStateContext", "TaskStateComposer", "main"):
        assert any(
            isinstance(node, (ast.ClassDef, ast.FunctionDef)) and node.name == definition
            for node in ast.walk(tree)
        ), definition

    assert "MemoryStore" not in source
    assert "StateStore" not in source
    assert "write_text(" not in source
    assert "json.dump(" not in source
    assert "register(" not in source
    assert "transact(" not in source


def test_legacy_task_state_module_is_adapter_only() -> None:
    source = ADAPTER_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(ADAPTER_PATH))
    definitions = {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
    }

    assert definitions == {"_load_canonical"}
    assert "brain_eleven.runtime.task_state_context" in source
    assert "from dataclasses" not in source
    assert "TaskStateComposer(" not in source
    assert "MemoryStore" not in source
    assert "StateStore" not in source
    assert "open(" not in source
    assert "write_text(" not in source
    assert "json.dump(" not in source
    assert ".register(" not in source
    assert ".transact(" not in source


def test_package_script_and_bare_surfaces_share_all_task_state_objects() -> None:
    canonical = importlib.import_module("brain_eleven.runtime.task_state_context")
    adapter = importlib.import_module("scripts.task_state_context")
    bare = importlib.import_module("task_state_context")

    for name in PUBLIC_NAMES:
        assert getattr(canonical, name) is getattr(adapter, name), name
        assert getattr(adapter, name) is getattr(bare, name), name

    assert canonical.TaskStateLineage.from_dict.__func__ is adapter.TaskStateLineage.from_dict.__func__
    assert canonical.TaskStateContext.__module__ == "brain_eleven.runtime.task_state_context"
    assert canonical.TaskStateComposer.__module__ == "brain_eleven.runtime.task_state_context"


def test_package_and_compatibility_composition_preserve_valid_archived_and_unknown_fixtures(tmp_path) -> None:
    canonical = importlib.import_module("brain_eleven.runtime.task_state_context")
    adapter = importlib.import_module("scripts.task_state_context")
    bare = importlib.import_module("task_state_context")

    project = tmp_path / "project-a"
    project.mkdir()
    ProjectRegistry(tmp_path).register(project, project_id="project-a")
    StateService(tmp_path).init_project(
        "project-a",
        source={"type": "user", "reference": "ig07-slice2f"},
        now="2026-09-17T10:00:00Z",
    )

    for module in (canonical, adapter, bare):
        result = module.TaskStateComposer(tmp_path, project).compose(
            "Implement safe task state composition."
        )
        assert result.state.status == "AVAILABLE"
        assert result.lineage.project_id == "project-a"
        if module is canonical:
            expected = _strip_generated_fields(result.to_dict())
    for module in (adapter, bare):
        actual = _strip_generated_fields(
            module.TaskStateComposer(tmp_path, project).compose(
                "Implement safe task state composition."
            ).to_dict()
        )
        assert actual == expected

    ProjectRegistry(tmp_path).set_status("project-a", "archived")
    archived = canonical.TaskStateComposer(tmp_path, project).compose(
        "Explain archived project state."
    )
    assert archived.task.project.status == "archived"
    assert archived.state.status == "PROJECT_ARCHIVED"

    unknown_root = tmp_path / "unknown"
    unknown = canonical.TaskStateComposer(tmp_path / "unknown-vault", unknown_root).compose(
        "Explain unresolved task state."
    )
    assert unknown.task.project.status == "unresolved"
    assert unknown.state.status == "PROJECT_UNKNOWN"
    assert unknown.lineage.to_dict() == {"status": "unresolved"}


def test_direct_adapter_and_package_cli_have_identical_json_contract(tmp_path) -> None:
    vault = tmp_path / "vault"
    project_root = tmp_path / "unknown-project"
    adapter = _run_cli(str(ADAPTER_PATH), vault, project_root, cwd=tmp_path)
    package = _run_cli("brain_eleven.runtime.task_state_context", vault, project_root, cwd=ROOT)

    assert adapter.returncode == 0, adapter.stderr
    assert package.returncode == 0, package.stderr
    assert _strip_generated_fields(json.loads(adapter.stdout)) == _strip_generated_fields(
        json.loads(package.stdout)
    )


def test_direct_adapter_and_package_cli_have_identical_human_contract(tmp_path) -> None:
    vault = tmp_path / "vault"
    project_root = tmp_path / "unknown-project"
    request = [
        "--vault",
        str(vault),
        "--project-root",
        str(project_root),
        "--request",
        "Explain task state.",
    ]
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    adapter = subprocess.run(
        [sys.executable, str(ADAPTER_PATH), *request],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    package = subprocess.run(
        [sys.executable, "-m", "brain_eleven.runtime.task_state_context", *request],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert adapter.returncode == 0, adapter.stderr
    assert package.returncode == 0, package.stderr
    assert adapter.stdout == package.stdout


def test_corrupt_registry_fails_closed_without_path_or_request_leak(tmp_path) -> None:
    vault = tmp_path / "vault"
    registry_path = vault / ".claude" / "project-registry.json"
    registry_path.parent.mkdir(parents=True)
    registry_path.write_text("{invalid registry", encoding="utf-8")
    project_root = tmp_path / "project"
    request = "private request must not appear in a registry failure"

    for command, cwd in (
        ([sys.executable, str(ADAPTER_PATH)], tmp_path),
        ([sys.executable, "-m", "brain_eleven.runtime.task_state_context"], ROOT),
    ):
        environment = os.environ.copy()
        environment.pop("PYTHONPATH", None)
        completed = subprocess.run(
            [
                *command,
                "--vault",
                str(vault),
                "--project-root",
                str(project_root),
                "--request",
                request,
                "--json",
            ],
            cwd=cwd,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        assert completed.returncode == 2
        assert json.loads(completed.stdout)["error"]["code"] == "TASK_STATE_ERROR"
        assert str(tmp_path) not in completed.stdout
        assert str(tmp_path) not in completed.stderr
        assert request not in completed.stdout
        assert request not in completed.stderr
