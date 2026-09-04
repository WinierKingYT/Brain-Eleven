"""Adapter for measuring the current ContextCompiler without changing it.

This module is the narrow boundary between production retrieval and Phase 15
evaluation.  It intentionally does *not* use a task prompt to rank memories:
the current compiler has no task-aware ranking, and the resulting limitation
must be visible in the baseline rather than hidden by the harness.
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import math
import sys
from pathlib import Path
from typing import Any, Mapping, Type

from .contracts import NormalizedEvaluationResult, SelectedContextItem
from .schema import GoldenTask


BASELINE_PROVIDER_ID = "context_compiler_baseline_v1"
DEFAULT_RETRIEVAL_SCOPE = "default"
_ROOT = Path(__file__).resolve().parents[1]
_SCRIPTS_DIRECTORY = _ROOT / "scripts"
_CONTEXT_COMPILER_PATH = _SCRIPTS_DIRECTORY / "context-compiler.py"
_MODULE_NAME = "brain_eleven_phase15_context_compiler"

BASELINE_CAPABILITIES = {
    "scope_isolation": "supported",
    "lifecycle_filtering": "supported",
    "task_aware_ranking": "unsupported",
    "authority_resolution": "unsupported",
    "conflict_resolution": "unsupported",
}


class BaselineAdapterError(RuntimeError):
    """Raised when the compiler projection cannot meet the evaluation contract."""


def _mapping(value: Any, field_name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise BaselineAdapterError(f"{field_name} must be an object")
    return value


def _required_string(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise BaselineAdapterError(f"{field_name} must be a non-empty string")
    return value.strip()


def _project_id(value: Any) -> str | None:
    if value is None or value == "":
        return None
    return _required_string(value, "memory project_id")


def _score(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise BaselineAdapterError("memory ranking_score must be numeric")
    score = float(value)
    if not math.isfinite(score):
        raise BaselineAdapterError("memory ranking_score must be finite")
    return score


def _load_context_compiler() -> Type[Any]:
    """Load the hyphenated production module by path without modifying it."""

    if not _CONTEXT_COMPILER_PATH.is_file():
        raise BaselineAdapterError(f"ContextCompiler not found: {_CONTEXT_COMPILER_PATH}")
    scripts_directory = str(_SCRIPTS_DIRECTORY)
    if scripts_directory not in sys.path:
        sys.path.insert(0, scripts_directory)

    module = sys.modules.get(_MODULE_NAME)
    if module is None:
        specification = importlib.util.spec_from_file_location(_MODULE_NAME, _CONTEXT_COMPILER_PATH)
        if specification is None or specification.loader is None:
            raise BaselineAdapterError("Cannot load ContextCompiler module specification")
        module = importlib.util.module_from_spec(specification)
        sys.modules[_MODULE_NAME] = module
        try:
            specification.loader.exec_module(module)
        except Exception:
            sys.modules.pop(_MODULE_NAME, None)
            raise

    context_compiler = getattr(module, "ContextCompiler", None)
    if context_compiler is None:
        raise BaselineAdapterError("ContextCompiler class is unavailable")
    return context_compiler


def _normalize_memory(memory: Mapping[str, Any]) -> SelectedContextItem:
    """Convert one compiler memory record into the independent result shape."""

    return SelectedContextItem(
        id=_required_string(memory.get("memory_id"), "memory_id"),
        source_type="memory",
        project_id=_project_id(memory.get("project_id")),
        memory_type=_required_string(memory.get("type"), "memory type"),
        status=_required_string(memory.get("status"), "memory status"),
        content=_required_string(memory.get("content"), "memory content"),
        score=_score(memory.get("ranking_score")),
    )


def normalize_context_compiler_output(
    task: GoldenTask,
    output: Mapping[str, Any],
) -> NormalizedEvaluationResult:
    """Validate and normalize a ContextCompiler projection for one golden task."""

    projection = _mapping(output, "ContextCompiler output")
    summary = _mapping(projection.get("summary"), "ContextCompiler output summary")
    if summary.get("project_id") != task.project_id:
        raise BaselineAdapterError("ContextCompiler output project_id does not match the evaluation task")
    if summary.get("retrieval_scope") != DEFAULT_RETRIEVAL_SCOPE:
        raise BaselineAdapterError("Baseline requires ContextCompiler default retrieval scope")

    source_revision = projection.get("source_memory_revision")
    if isinstance(source_revision, bool) or not isinstance(source_revision, int) or source_revision < 0:
        raise BaselineAdapterError("ContextCompiler source_memory_revision must be a non-negative integer")
    top_memories = projection.get("top_memories")
    if not isinstance(top_memories, list):
        raise BaselineAdapterError("ContextCompiler top_memories must be an array")
    selected_items = tuple(
        _normalize_memory(_mapping(memory, f"ContextCompiler top_memories[{index}]"))
        for index, memory in enumerate(top_memories)
    )
    return NormalizedEvaluationResult(
        task_id=task.task_id,
        provider_id=BASELINE_PROVIDER_ID,
        selected_items=selected_items,
        source_memory_revision=source_revision,
        project_id=task.project_id,
        retrieval_scope=DEFAULT_RETRIEVAL_SCOPE,
        capabilities=BASELINE_CAPABILITIES,
    )


class BaselineContextProvider:
    """Run the current compiler and expose only the normalized selection result."""

    provider_id = BASELINE_PROVIDER_ID

    def select(self, task: GoldenTask, vault_path: Path | str) -> NormalizedEvaluationResult:
        """Select baseline context for ``task`` from a synthetic vault.

        ``task.prompt`` is deliberately not supplied to the compiler.  This
        preserves a truthful baseline for the current non-task-aware compiler.
        """

        vault = Path(vault_path)
        if not vault.is_dir():
            raise BaselineAdapterError(f"evaluation vault must be a directory: {vault}")

        compiler_class = _load_context_compiler()
        compiler = compiler_class(
            str(vault),
            project_id=task.project_id,
            retrieval_scope=DEFAULT_RETRIEVAL_SCOPE,
        )
        # The production compiler is intentionally chatty for hook execution.
        # Evaluation reports own their output channel, so retain no console
        # noise while preserving the compiler's in-memory result unchanged.
        with contextlib.redirect_stdout(io.StringIO()):
            output = compiler.compile()
        return normalize_context_compiler_output(task, output)
