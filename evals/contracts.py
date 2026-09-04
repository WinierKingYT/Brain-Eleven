"""Production-independent result contracts for offline context evaluation.

Providers translate their own retrieval output into these small immutable
objects.  The evaluator can then calculate metrics without importing or
depending on any production retrieval implementation.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Mapping, Optional


NORMALIZED_RESULT_SCHEMA_VERSION = 1


class EvaluationResultContractError(ValueError):
    """Raised when a provider tries to emit an invalid normalized result."""


def _required_string(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise EvaluationResultContractError(f"{field_name} must be a non-empty string")
    return value.strip()


def _optional_string(value: Any, field_name: str) -> Optional[str]:
    if value is None or value == "":
        return None
    return _required_string(value, field_name)


def _score(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise EvaluationResultContractError("selected item score must be numeric")
    score = float(value)
    if not math.isfinite(score):
        raise EvaluationResultContractError("selected item score must be finite")
    return score


@dataclass(frozen=True)
class SelectedContextItem:
    """One provider-selected item in the stable evaluation representation."""

    id: str
    source_type: str
    project_id: Optional[str]
    memory_type: str
    status: str
    content: str
    score: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", _required_string(self.id, "selected item id"))
        object.__setattr__(self, "source_type", _required_string(self.source_type, "source_type"))
        object.__setattr__(self, "project_id", _optional_string(self.project_id, "project_id"))
        object.__setattr__(self, "memory_type", _required_string(self.memory_type, "memory_type"))
        object.__setattr__(self, "status", _required_string(self.status, "status"))
        object.__setattr__(self, "content", _required_string(self.content, "content"))
        object.__setattr__(self, "score", _score(self.score))

    def as_dict(self) -> dict[str, Any]:
        """Return the machine-readable item representation."""

        return {
            "id": self.id,
            "source_type": self.source_type,
            "project_id": self.project_id,
            "memory_type": self.memory_type,
            "status": self.status,
            "content": self.content,
            "score": self.score,
        }


@dataclass(frozen=True)
class NormalizedEvaluationResult:
    """Stable provider output consumed by the Phase 15 evaluator."""

    task_id: str
    provider_id: str
    selected_items: tuple[SelectedContextItem, ...]
    source_memory_revision: int
    project_id: Optional[str]
    retrieval_scope: str
    capabilities: Mapping[str, str]
    schema_version: int = NORMALIZED_RESULT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "task_id", _required_string(self.task_id, "task_id"))
        object.__setattr__(self, "provider_id", _required_string(self.provider_id, "provider_id"))
        object.__setattr__(self, "project_id", _optional_string(self.project_id, "project_id"))
        object.__setattr__(self, "retrieval_scope", _required_string(self.retrieval_scope, "retrieval_scope"))
        if self.schema_version != NORMALIZED_RESULT_SCHEMA_VERSION:
            raise EvaluationResultContractError(
                f"schema_version must be {NORMALIZED_RESULT_SCHEMA_VERSION}"
            )
        if isinstance(self.source_memory_revision, bool) or not isinstance(
            self.source_memory_revision, int
        ) or self.source_memory_revision < 0:
            raise EvaluationResultContractError(
                "source_memory_revision must be a non-negative integer"
            )
        if not isinstance(self.capabilities, Mapping):
            raise EvaluationResultContractError("capabilities must be a mapping")
        normalized_capabilities: dict[str, str] = {}
        for name, state in self.capabilities.items():
            normalized_name = _required_string(name, "capability name")
            normalized_capabilities[normalized_name] = _required_string(
                state, f"capability {normalized_name} state"
            )
        object.__setattr__(self, "capabilities", normalized_capabilities)

        items = tuple(self.selected_items)
        if not all(isinstance(item, SelectedContextItem) for item in items):
            raise EvaluationResultContractError("selected_items must contain SelectedContextItem values")
        ids = tuple(item.id for item in items)
        if len(ids) != len(set(ids)):
            raise EvaluationResultContractError("selected_items must not contain duplicate ids")
        object.__setattr__(self, "selected_items", items)

    def as_dict(self) -> dict[str, Any]:
        """Return a deterministic, machine-readable evaluation result."""

        return {
            "schema_version": self.schema_version,
            "task_id": self.task_id,
            "provider_id": self.provider_id,
            "source_memory_revision": self.source_memory_revision,
            "project_id": self.project_id,
            "retrieval_scope": self.retrieval_scope,
            "capabilities": dict(sorted(self.capabilities.items())),
            "selected_items": [item.as_dict() for item in self.selected_items],
        }
