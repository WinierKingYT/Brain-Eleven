"""Content-free contracts for local private real-use evaluation.

Only identifiers and labels are persisted.  The private corpus may point at
local task/memory records, but it deliberately does not contain their text.
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence


PRIVATE_EVAL_SCHEMA_VERSION = 1
ANNOTATION_LABELS = frozenset({"required", "helpful", "noise", "forbidden"})
_FORBIDDEN_KEYS = frozenset(
    {
        "content", "prompt", "text", "transcript", "raw", "body", "message",
        "rendered_context", "rendered_text", "secret", "token", "password",
    }
)


class PrivateEvaluationError(ValueError):
    """A private evaluation record is invalid or violates the privacy boundary."""


def _string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip() or "\n" in value or "\r" in value:
        raise PrivateEvaluationError(f"{field} must be a single non-empty line")
    return value.strip()


def _optional_string(value: Any, field: str) -> Optional[str]:
    if value is None or value == "":
        return None
    return _string(value, field)


def _ids(value: Any, field: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise PrivateEvaluationError(f"{field} must be an array")
    result = tuple(_string(item, f"{field}[{index}]") for index, item in enumerate(value))
    if len(result) != len(set(result)):
        raise PrivateEvaluationError(f"{field} must not contain duplicate identifiers")
    return result


def _ensure_content_free(value: Any, location: str = "record") -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            if str(key).casefold() in _FORBIDDEN_KEYS:
                raise PrivateEvaluationError(f"{location} contains forbidden private field {key!r}")
            _ensure_content_free(child, f"{location}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _ensure_content_free(child, f"{location}[{index}]")


def _private_path(path: Path, private_root: Path) -> Path:
    candidate = path.expanduser().resolve(strict=False)
    root = private_root.expanduser().resolve(strict=False)
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise PrivateEvaluationError("private evaluation data must stay under evals/private") from exc
    if candidate == root:
        raise PrivateEvaluationError("private evaluation path must name a file")
    return candidate


@dataclass(frozen=True)
class PrivateAnnotation:
    memory_id: str
    label: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "memory_id", _string(self.memory_id, "annotation.memory_id"))
        label = _string(self.label, "annotation.label").casefold()
        if label not in ANNOTATION_LABELS:
            raise PrivateEvaluationError(f"unsupported annotation label: {label}")
        object.__setattr__(self, "label", label)

    def as_dict(self) -> dict[str, str]:
        return {"memory_id": self.memory_id, "label": self.label}


@dataclass(frozen=True)
class PrivateEvaluationCase:
    """A local-only case containing IDs and human labels, never memory text."""

    case_id: str
    task_id: str
    project_id: Optional[str]
    selected_memory_ids: tuple[str, ...]
    annotations: tuple[PrivateAnnotation, ...]
    schema_version: int = PRIVATE_EVAL_SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "case_id", _string(self.case_id, "case_id"))
        object.__setattr__(self, "task_id", _string(self.task_id, "task_id"))
        object.__setattr__(self, "project_id", _optional_string(self.project_id, "project_id"))
        if self.schema_version != PRIVATE_EVAL_SCHEMA_VERSION:
            raise PrivateEvaluationError("unsupported private evaluation schema")
        selected = tuple(self.selected_memory_ids)
        if len(selected) != len(set(selected)):
            raise PrivateEvaluationError("selected_memory_ids must not contain duplicates")
        if not all(isinstance(item, str) and item.strip() for item in selected):
            raise PrivateEvaluationError("selected_memory_ids must contain identifiers")
        object.__setattr__(self, "selected_memory_ids", selected)
        annotations = tuple(self.annotations)
        if not all(isinstance(item, PrivateAnnotation) for item in annotations):
            raise PrivateEvaluationError("annotations must contain PrivateAnnotation values")
        annotation_ids = [item.memory_id for item in annotations]
        if len(annotation_ids) != len(set(annotation_ids)):
            raise PrivateEvaluationError("each memory may have only one private label")
        object.__setattr__(self, "annotations", annotations)

    @classmethod
    def empty(cls, case_id: str, task_id: str, project_id: Optional[str] = None) -> "PrivateEvaluationCase":
        return cls(case_id, task_id, project_id, (), ())

    def with_annotation(self, memory_id: str, label: str) -> "PrivateEvaluationCase":
        annotation = PrivateAnnotation(memory_id, label)
        remaining = tuple(item for item in self.annotations if item.memory_id != annotation.memory_id)
        return PrivateEvaluationCase(
            self.case_id,
            self.task_id,
            self.project_id,
            self.selected_memory_ids,
            tuple(sorted((*remaining, annotation), key=lambda item: item.memory_id)),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "case_id": self.case_id,
            "task_id": self.task_id,
            "project_id": self.project_id,
            "selected_memory_ids": list(self.selected_memory_ids),
            "annotations": [item.as_dict() for item in self.annotations],
        }


def parse_case(document: Mapping[str, Any]) -> PrivateEvaluationCase:
    _ensure_content_free(document)
    required = {"schema_version", "case_id", "task_id", "project_id", "selected_memory_ids", "annotations"}
    if set(document) != required:
        raise PrivateEvaluationError("private evaluation case has invalid fields")
    raw_annotations = document["annotations"]
    if not isinstance(raw_annotations, list):
        raise PrivateEvaluationError("annotations must be an array")
    annotations: list[PrivateAnnotation] = []
    for index, item in enumerate(raw_annotations):
        if not isinstance(item, Mapping) or set(item) != {"memory_id", "label"}:
            raise PrivateEvaluationError(f"annotations[{index}] is malformed")
        annotations.append(PrivateAnnotation(item["memory_id"], item["label"]))
    return PrivateEvaluationCase(
        document["case_id"],
        document["task_id"],
        document["project_id"],
        _ids(document["selected_memory_ids"], "selected_memory_ids"),
        tuple(annotations),
        document["schema_version"],
    )


def load_case(path: str | Path, *, private_root: str | Path = "evals/private") -> PrivateEvaluationCase:
    candidate = _private_path(Path(path), Path(private_root))
    try:
        document = json.loads(candidate.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PrivateEvaluationError("private evaluation case is unreadable") from exc
    if not isinstance(document, Mapping):
        raise PrivateEvaluationError("private evaluation case must be an object")
    return parse_case(document)


def write_case(case: PrivateEvaluationCase, path: str | Path, *, private_root: str | Path = "evals/private") -> Path:
    candidate = _private_path(Path(path), Path(private_root))
    _ensure_content_free(case.as_dict())
    candidate.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{candidate.name}.", suffix=".tmp", dir=str(candidate.parent))
    temporary_path = Path(temporary)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(case.as_dict(), handle, ensure_ascii=False, sort_keys=True, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, candidate)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()
    return candidate


def evaluate_case(case: PrivateEvaluationCase, selected_memory_ids: Sequence[str] | None = None) -> dict[str, Any]:
    """Return deterministic, content-free real-use quality measurements."""
    selected = tuple(selected_memory_ids if selected_memory_ids is not None else case.selected_memory_ids)
    if len(selected) != len(set(selected)):
        raise PrivateEvaluationError("evaluation selection contains duplicate identifiers")
    selected_set = set(selected)
    labels = {item.memory_id: item.label for item in case.annotations}
    required = {memory_id for memory_id, label in labels.items() if label == "required"}
    relevant = {memory_id for memory_id, label in labels.items() if label in {"required", "helpful"}}
    forbidden = {memory_id for memory_id, label in labels.items() if label == "forbidden"}
    noise = {memory_id for memory_id, label in labels.items() if label == "noise"}
    required_selected = selected_set & required
    relevant_selected = selected_set & relevant
    forbidden_selected = selected_set & forbidden
    noise_selected = selected_set & noise
    return {
        "schema_version": PRIVATE_EVAL_SCHEMA_VERSION,
        "case_id": case.case_id,
        "task_id": case.task_id,
        "project_id": case.project_id,
        "selected_count": len(selected),
        "required_count": len(required),
        "required_recall": len(required_selected) / len(required) if required else 1.0,
        "relevant_precision": len(relevant_selected) / len(selected) if selected else 1.0,
        "forbidden_selected": len(forbidden_selected),
        "noise_selected": len(noise_selected),
        "unknown_selected": len(selected_set - set(labels)),
        "hard_gates": {
            "forbidden_leakage": len(forbidden_selected) == 0,
            "duplicate_selection": len(selected) == len(selected_set),
        },
    }
