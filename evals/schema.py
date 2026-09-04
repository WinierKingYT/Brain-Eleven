"""Strict, offline contracts for the public Phase 15 evaluation corpus.

The evaluator deliberately owns this schema instead of importing production
retrieval types. That keeps benchmark labels independent from the algorithm
being measured and makes corpus validation reproducible without network access.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional, Sequence


SCHEMA_VERSION = 1
MEMORY_TYPES = frozenset({"decision", "lesson", "open_loop", "observation"})
MEMORY_STATUSES = frozenset({"active", "resolved", "superseded"})
MEMORY_SCOPES = frozenset({"global", "project"})
PROJECT_STATUSES = frozenset({"active", "archived"})


class CorpusValidationError(ValueError):
    """Raised when a public evaluation fixture or golden task is incoherent."""


@dataclass(frozen=True)
class FixtureMemory:
    """The minimal canonical-memory shape available to a synthetic vault."""

    memory_id: str
    memory_type: str
    status: str
    content: str
    scope: str
    project_id: Optional[str]


@dataclass(frozen=True)
class VaultFixture:
    """A named, synthetic vault and its stable project/memory identities."""

    fixture_id: str
    project_ids: frozenset[str]
    memories: Mapping[str, FixtureMemory]


@dataclass(frozen=True)
class GoldenTask:
    """Ground truth for one context-selection task."""

    task_id: str
    project_id: Optional[str]
    prompt: str
    intent: tuple[str, ...]
    domains: tuple[str, ...]
    required: tuple[str, ...]
    useful: tuple[str, ...]
    forbidden: tuple[str, ...]
    wrong_project_allowed: bool
    inactive_allowed: bool
    expectations: Mapping[str, Any]


def _error(location: str, message: str) -> CorpusValidationError:
    return CorpusValidationError(f"{location}: {message}")


def _mapping(value: Any, location: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise _error(location, "must be an object")
    return value


def _strict_keys(
    value: Mapping[str, Any],
    *,
    location: str,
    required: set[str],
    optional: set[str] = frozenset(),
) -> None:
    missing = required - value.keys()
    if missing:
        raise _error(location, f"missing required field(s): {', '.join(sorted(missing))}")
    unknown = value.keys() - required - optional
    if unknown:
        raise _error(location, f"unknown field(s): {', '.join(sorted(unknown))}")


def _nonempty_string(value: Any, location: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise _error(location, "must be a non-empty string")
    return value.strip()


def _string_list(value: Any, location: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise _error(location, "must be an array")
    result = tuple(_nonempty_string(item, f"{location}[{index}]") for index, item in enumerate(value))
    if len(result) != len(set(result)):
        raise _error(location, "must not contain duplicate values")
    return result


def _schema_version(document: Mapping[str, Any], location: str) -> None:
    if document.get("schema_version") != SCHEMA_VERSION:
        raise _error(location, f"schema_version must be {SCHEMA_VERSION}")


def _optional_project_id(value: Any, location: str) -> Optional[str]:
    if value is None:
        return None
    return _nonempty_string(value, location)


def parse_fixture(document: Mapping[str, Any], location: str = "fixture") -> VaultFixture:
    """Parse and validate one synthetic-vault document without touching disk."""

    document = _mapping(document, location)
    _strict_keys(
        document,
        location=location,
        required={"schema_version", "fixture_id", "projects", "memories"},
    )
    _schema_version(document, location)
    fixture_id = _nonempty_string(document["fixture_id"], f"{location}.fixture_id")

    projects_value = document["projects"]
    if not isinstance(projects_value, list):
        raise _error(f"{location}.projects", "must be an array")
    project_ids: set[str] = set()
    for index, project_value in enumerate(projects_value):
        project = _mapping(project_value, f"{location}.projects[{index}]")
        _strict_keys(
            project,
            location=f"{location}.projects[{index}]",
            required={"project_id", "status"},
        )
        project_id = _nonempty_string(project["project_id"], f"{location}.projects[{index}].project_id")
        if project_id in project_ids:
            raise _error(f"{location}.projects", f"duplicate project_id: {project_id}")
        if project["status"] not in PROJECT_STATUSES:
            raise _error(
                f"{location}.projects[{index}].status",
                f"must be one of: {', '.join(sorted(PROJECT_STATUSES))}",
            )
        project_ids.add(project_id)

    memories_value = document["memories"]
    if not isinstance(memories_value, list):
        raise _error(f"{location}.memories", "must be an array")
    memories: dict[str, FixtureMemory] = {}
    for index, memory_value in enumerate(memories_value):
        memory = _mapping(memory_value, f"{location}.memories[{index}]")
        _strict_keys(
            memory,
            location=f"{location}.memories[{index}]",
            required={"memory_id", "type", "status", "content", "scope"},
            optional={"project_id"},
        )
        memory_id = _nonempty_string(memory["memory_id"], f"{location}.memories[{index}].memory_id")
        if memory_id in memories:
            raise _error(f"{location}.memories", f"duplicate memory_id: {memory_id}")
        memory_type = memory["type"]
        if memory_type not in MEMORY_TYPES:
            raise _error(
                f"{location}.memories[{index}].type",
                f"must be one of: {', '.join(sorted(MEMORY_TYPES))}",
            )
        status = memory["status"]
        if status not in MEMORY_STATUSES:
            raise _error(
                f"{location}.memories[{index}].status",
                f"must be one of: {', '.join(sorted(MEMORY_STATUSES))}",
            )
        scope = memory["scope"]
        if scope not in MEMORY_SCOPES:
            raise _error(
                f"{location}.memories[{index}].scope",
                f"must be one of: {', '.join(sorted(MEMORY_SCOPES))}",
            )
        project_id = _optional_project_id(memory.get("project_id"), f"{location}.memories[{index}].project_id")
        if scope == "global" and project_id is not None:
            raise _error(f"{location}.memories[{index}]", "global memory must not have project_id")
        if scope == "project":
            if project_id is None:
                raise _error(f"{location}.memories[{index}]", "project memory requires project_id")
            if project_id not in project_ids:
                raise _error(f"{location}.memories[{index}]", f"unknown project_id: {project_id}")
        memories[memory_id] = FixtureMemory(
            memory_id=memory_id,
            memory_type=memory_type,
            status=status,
            content=_nonempty_string(memory["content"], f"{location}.memories[{index}].content"),
            scope=scope,
            project_id=project_id,
        )

    return VaultFixture(
        fixture_id=fixture_id,
        project_ids=frozenset(project_ids),
        memories=memories,
    )


def validate_fixture_documents(documents: Iterable[Mapping[str, Any]]) -> tuple[VaultFixture, ...]:
    """Validate a fixture collection and reject duplicate fixture identities."""

    fixtures: list[VaultFixture] = []
    fixture_ids: set[str] = set()
    for index, document in enumerate(documents):
        fixture = parse_fixture(document, f"fixtures[{index}]")
        if fixture.fixture_id in fixture_ids:
            raise _error("fixtures", f"duplicate fixture_id: {fixture.fixture_id}")
        fixture_ids.add(fixture.fixture_id)
        fixtures.append(fixture)
    return tuple(fixtures)


def parse_task(
    document: Mapping[str, Any],
    fixture: VaultFixture,
    location: str = "task",
) -> GoldenTask:
    """Parse a golden task and validate all labels against its fixture."""

    document = _mapping(document, location)
    _strict_keys(
        document,
        location=location,
        required={"schema_version", "task_id", "task", "expected_context", "expected_behavior"},
        optional={"expectations"},
    )
    _schema_version(document, location)
    task_id = _nonempty_string(document["task_id"], f"{location}.task_id")

    task = _mapping(document["task"], f"{location}.task")
    _strict_keys(
        task,
        location=f"{location}.task",
        required={"project_id", "prompt", "intent", "domains"},
    )
    project_id = _optional_project_id(task["project_id"], f"{location}.task.project_id")
    if project_id is not None and project_id not in fixture.project_ids:
        raise _error(f"{location}.task.project_id", f"unknown project_id: {project_id}")

    expected_context = _mapping(document["expected_context"], f"{location}.expected_context")
    _strict_keys(
        expected_context,
        location=f"{location}.expected_context",
        required={"required", "useful", "forbidden"},
    )
    required = _string_list(expected_context["required"], f"{location}.expected_context.required")
    useful = _string_list(expected_context["useful"], f"{location}.expected_context.useful")
    forbidden = _string_list(expected_context["forbidden"], f"{location}.expected_context.forbidden")
    if not required and not useful and not forbidden:
        raise _error(f"{location}.expected_context", "must contain at least one labeled memory")
    labels = {"required": set(required), "useful": set(useful), "forbidden": set(forbidden)}
    for first, second in (("required", "useful"), ("required", "forbidden"), ("useful", "forbidden")):
        overlap = labels[first] & labels[second]
        if overlap:
            raise _error(
                f"{location}.expected_context",
                f"memory cannot be both {first} and {second}: {', '.join(sorted(overlap))}",
            )
    unknown_memory_ids = (labels["required"] | labels["useful"] | labels["forbidden"]) - fixture.memories.keys()
    if unknown_memory_ids:
        raise _error(
            f"{location}.expected_context",
            f"unknown memory_id(s): {', '.join(sorted(unknown_memory_ids))}",
        )

    behavior = _mapping(document["expected_behavior"], f"{location}.expected_behavior")
    _strict_keys(
        behavior,
        location=f"{location}.expected_behavior",
        required=set(),
        optional={"wrong_project_allowed", "inactive_allowed"},
    )
    wrong_project_allowed = behavior.get("wrong_project_allowed", False)
    inactive_allowed = behavior.get("inactive_allowed", False)
    if not isinstance(wrong_project_allowed, bool):
        raise _error(f"{location}.expected_behavior.wrong_project_allowed", "must be boolean")
    if not isinstance(inactive_allowed, bool):
        raise _error(f"{location}.expected_behavior.inactive_allowed", "must be boolean")

    expectations = document.get("expectations", {})
    expectations = _mapping(expectations, f"{location}.expectations")
    _strict_keys(
        expectations,
        location=f"{location}.expectations",
        required=set(),
        optional={"authority_resolution", "conflict_resolution", "ask_user", "abstain"},
    )
    for field in ("authority_resolution", "conflict_resolution"):
        if field in expectations and expectations[field] != "future":
            raise _error(f"{location}.expectations.{field}", 'must be "future"')
    for field in ("ask_user", "abstain"):
        if field in expectations and not isinstance(expectations[field], bool):
            raise _error(f"{location}.expectations.{field}", "must be boolean")

    return GoldenTask(
        task_id=task_id,
        project_id=project_id,
        prompt=_nonempty_string(task["prompt"], f"{location}.task.prompt"),
        intent=_string_list(task["intent"], f"{location}.task.intent"),
        domains=_string_list(task["domains"], f"{location}.task.domains"),
        required=required,
        useful=useful,
        forbidden=forbidden,
        wrong_project_allowed=wrong_project_allowed,
        inactive_allowed=inactive_allowed,
        expectations=dict(expectations),
    )


def validate_task_documents(
    documents: Iterable[Mapping[str, Any]], fixture: VaultFixture
) -> tuple[GoldenTask, ...]:
    """Validate a suite and reject duplicate task identities before evaluation."""

    tasks: list[GoldenTask] = []
    task_ids: set[str] = set()
    for index, document in enumerate(documents):
        task = parse_task(document, fixture, f"tasks[{index}]")
        if task.task_id in task_ids:
            raise _error("tasks", f"duplicate task_id: {task.task_id}")
        task_ids.add(task.task_id)
        tasks.append(task)
    return tuple(tasks)


def _load_json(path: Path) -> Mapping[str, Any]:
    try:
        content = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise CorpusValidationError(f"{path}: invalid JSON: {error}") from error
    return _mapping(content, str(path))


def load_fixture(path: Path | str) -> VaultFixture:
    """Load a fixture document from disk."""

    fixture_path = Path(path)
    return parse_fixture(_load_json(fixture_path), str(fixture_path))


def load_tasks(paths: Sequence[Path | str], fixture: VaultFixture) -> tuple[GoldenTask, ...]:
    """Load task files in stable path order for deterministic evaluation runs."""

    documents = [_load_json(Path(path)) for path in sorted((Path(path) for path in paths), key=lambda item: str(item))]
    return validate_task_documents(documents, fixture)
