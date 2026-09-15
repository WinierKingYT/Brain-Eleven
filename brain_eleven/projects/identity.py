"""Content-free project identity and registry-lineage validation helpers.

The registry remains the only authority for project roots and stable project
IDs.  This module derives an opaque identity from a normalized root and
validates a read-only ``TaskStateContext`` against a fresh registry snapshot.
It deliberately never persists a root, mutates the registry, or includes a
filesystem path in a returned error.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import re
from pathlib import Path
from typing import Any, Mapping, Optional

from .registry import ProjectRegistry, ProjectRegistryError, normalize_registry_root


ROOT_IDENTITY_PREFIX = "project-root-v1:"
ROOT_IDENTITY_PATTERN = re.compile(r"^project-root-v1:[0-9a-f]{64}$")
LINEAGE_STATUSES = frozenset({"resolved", "unresolved", "global"})


class ProjectLineageError(ValueError):
    """Raised when a context cannot be trusted for the current registry."""

    def __init__(self, message: str, *, code: str = "STALE_INPUT") -> None:
        # Callers may expose this message in content-free telemetry.  Keep
        # the vocabulary bounded and never interpolate a path or exception.
        self.code = code
        super().__init__(message)


@dataclass(frozen=True)
class RegistryLineage:
    """The opaque registry facts attached to one composed context."""

    status: str
    project_id: Optional[str]
    registry_revision: Optional[int]
    root_identity: Optional[str]


@dataclass(frozen=True)
class RegistrySnapshot:
    """A private, read-only registry observation used during composition."""

    status: str
    project_id: Optional[str]
    normalized_root: Optional[str]
    registry_revision: int
    root_identity: Optional[str]


def project_root_identity(project_root: str | Path) -> str:
    """Return a stable, domain-separated digest for a registry root.

    Only the normalized root enters the digest.  The returned value has a
    fixed, opaque format and is safe to place in a content-free context
    envelope.  A caller that cannot normalize the root receives a bounded
    lineage error rather than a path-bearing filesystem exception.
    """
    try:
        normalized = normalize_registry_root(project_root)
        digest = hashlib.sha256(
            b"brain-eleven:project-root-v1\0" + normalized.encode("utf-8")
        ).hexdigest()
    except (OSError, TypeError, ValueError, UnicodeError) as exc:
        raise ProjectLineageError("Project root identity is unavailable", code="SCOPE_ERROR") from exc
    return ROOT_IDENTITY_PREFIX + digest


# Short aliases make the utility easy to discover without introducing a
# second implementation or a second hashing rule.
root_identity = project_root_identity
compute_project_root_identity = project_root_identity


def _valid_revision(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _record_for_root(document: Mapping[str, Any], normalized_root: str) -> Optional[Mapping[str, Any]]:
    projects = document.get("projects")
    if not isinstance(projects, list):
        raise ProjectLineageError("Project registry identity is invalid", code="SCOPE_ERROR")
    return next(
        (record for record in projects if isinstance(record, Mapping) and record.get("root") == normalized_root),
        None,
    )


def registry_snapshot_for_root(vault_path: str | Path, project_root: str | Path) -> RegistrySnapshot:
    """Read one registry snapshot and resolve the supplied root in it."""
    try:
        normalized_root = normalize_registry_root(project_root)
        document = ProjectRegistry(vault_path).load()
    except ProjectRegistryError as exc:
        raise ProjectLineageError("Project registry is unavailable", code="SCOPE_ERROR") from exc
    except (OSError, TypeError, ValueError, UnicodeError) as exc:
        raise ProjectLineageError("Project registry identity is unavailable", code="SCOPE_ERROR") from exc

    revision = document.get("revision")
    if not _valid_revision(revision):
        raise ProjectLineageError("Project registry identity is invalid", code="SCOPE_ERROR")
    record = _record_for_root(document, normalized_root)
    if record is None:
        return RegistrySnapshot(
            status="unresolved",
            project_id=None,
            normalized_root=None,
            registry_revision=revision,
            root_identity=None,
        )
    project_id = record.get("project_id")
    status = record.get("status")
    root = record.get("root")
    if not isinstance(project_id, str) or not project_id.strip() or status not in {"active", "archived"}:
        raise ProjectLineageError("Project registry identity is invalid", code="SCOPE_ERROR")
    if not isinstance(root, str) or root != normalized_root:
        raise ProjectLineageError("Project registry identity is invalid", code="SCOPE_ERROR")
    try:
        identity = project_root_identity(root)
    except ProjectLineageError:
        raise ProjectLineageError("Project registry identity is invalid", code="SCOPE_ERROR") from None
    return RegistrySnapshot(
        status="resolved" if status == "active" else "archived",
        project_id=project_id,
        normalized_root=normalized_root,
        registry_revision=revision,
        root_identity=identity,
    )


def _record_for_project(document: Mapping[str, Any], project_id: str) -> Optional[Mapping[str, Any]]:
    projects = document.get("projects")
    if not isinstance(projects, list):
        raise ProjectLineageError("Project registry identity is invalid", code="SCOPE_ERROR")
    return next(
        (
            record
            for record in projects
            if isinstance(record, Mapping) and record.get("project_id") == project_id
        ),
        None,
    )


def _read_current_lineage(vault_path: str | Path, project_id: str) -> RegistryLineage:
    try:
        document = ProjectRegistry(vault_path).load()
    except ProjectRegistryError as exc:
        raise ProjectLineageError("Project registry is unavailable", code="SCOPE_ERROR") from exc
    except (OSError, TypeError, ValueError, UnicodeError) as exc:
        raise ProjectLineageError("Project registry identity is unavailable", code="SCOPE_ERROR") from exc
    revision = document.get("revision")
    if not _valid_revision(revision):
        raise ProjectLineageError("Project registry identity is invalid", code="SCOPE_ERROR")
    record = _record_for_project(document, project_id)
    if record is None:
        raise ProjectLineageError("Project identity is no longer registered", code="STALE_INPUT")
    root = record.get("root")
    status = record.get("status")
    if (
        not isinstance(root, str)
        or status not in {"active", "archived"}
        or not isinstance(record.get("project_id"), str)
    ):
        raise ProjectLineageError("Project registry identity is invalid", code="SCOPE_ERROR")
    try:
        identity = project_root_identity(root)
    except ProjectLineageError:
        raise ProjectLineageError("Project registry identity is invalid", code="SCOPE_ERROR") from None
    return RegistryLineage(
        status="resolved" if status == "active" else "archived",
        project_id=project_id,
        registry_revision=revision,
        root_identity=identity,
    )


def validate_task_state_lineage(vault_path: str | Path, task_state: Any) -> RegistryLineage:
    """Validate a context's opaque lineage against the current registry.

    The function is read-only and intentionally conservative: any registry
    revision change since composition is stale, including a change to an
    unrelated project.  Unresolved/global contexts are explicit and carry no
    project identity, so they cannot be widened into a project route here.
    """
    lineage = getattr(task_state, "lineage", None)
    if lineage is None:
        raise ProjectLineageError("TaskStateContext lineage is required", code="IDENTITY_REQUIRED")

    status = getattr(lineage, "status", None)
    project_id = getattr(lineage, "project_id", None)
    registry_revision = getattr(lineage, "registry_revision", None)
    expected_root_identity = getattr(lineage, "root_identity", None)
    task = getattr(task_state, "task", None)
    state = getattr(task_state, "state", None)
    task_project = getattr(getattr(task, "project", None), "project_id", None)
    state_project = getattr(state, "project_id", None)

    if status in {"unresolved", "global"}:
        if project_id is not None or registry_revision is not None or expected_root_identity is not None:
            raise ProjectLineageError("Non-resolved lineage contains project identity", code="SCOPE_ERROR")
        if task_project is not None or state_project is not None:
            raise ProjectLineageError("Global lineage contains project identity", code="SCOPE_ERROR")
        return RegistryLineage(status=status, project_id=None, registry_revision=None, root_identity=None)

    if status != "resolved" or not isinstance(project_id, str) or not project_id.strip():
        raise ProjectLineageError("TaskStateContext lineage is invalid", code="IDENTITY_REQUIRED")
    if not _valid_revision(registry_revision) or not isinstance(expected_root_identity, str):
        raise ProjectLineageError("TaskStateContext lineage is invalid", code="IDENTITY_REQUIRED")
    if not ROOT_IDENTITY_PATTERN.fullmatch(expected_root_identity):
        raise ProjectLineageError("TaskStateContext root identity is invalid", code="IDENTITY_REQUIRED")
    if task_project != project_id or state_project != project_id:
        raise ProjectLineageError("Task and state project identity does not match", code="SCOPE_ERROR")

    current = _read_current_lineage(vault_path, project_id)
    if current.registry_revision != registry_revision:
        raise ProjectLineageError("TaskStateContext registry lineage is stale", code="STALE_INPUT")
    if current.root_identity != expected_root_identity:
        raise ProjectLineageError("TaskStateContext root lineage is stale", code="STALE_INPUT")
    return current


def lineage_to_dict(lineage: RegistryLineage) -> dict[str, Any]:
    """Serialize validated lineage without exposing a filesystem path."""
    if lineage.status in {"unresolved", "global"}:
        return {"status": lineage.status}
    if (
        lineage.status != "resolved"
        or not isinstance(lineage.project_id, str)
        or not _valid_revision(lineage.registry_revision)
        or not isinstance(lineage.root_identity, str)
        or not ROOT_IDENTITY_PATTERN.fullmatch(lineage.root_identity)
    ):
        raise ProjectLineageError("TaskStateContext lineage is invalid", code="IDENTITY_REQUIRED")
    return {
        "project_id": lineage.project_id,
        "registry_revision": lineage.registry_revision,
        "root_identity": lineage.root_identity,
    }


__all__ = [
    "LINEAGE_STATUSES",
    "ROOT_IDENTITY_PATTERN",
    "ROOT_IDENTITY_PREFIX",
    "ProjectLineageError",
    "RegistryLineage",
    "RegistrySnapshot",
    "compute_project_root_identity",
    "lineage_to_dict",
    "project_root_identity",
    "registry_snapshot_for_root",
    "root_identity",
    "validate_task_state_lineage",
]
