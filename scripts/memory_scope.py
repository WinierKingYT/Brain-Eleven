#!/usr/bin/env python3
"""Shared scope, project identity and retrieval policy for Brain-Eleven."""

import hashlib
import os
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple, Union


GLOBAL_SCOPE = "global"
PROJECT_SCOPE = "project"
DEFAULT_RETRIEVAL_SCOPE = "default"
GLOBAL_RETRIEVAL_SCOPE = "global"
PROJECT_RETRIEVAL_SCOPE = "project"
ALL_RETRIEVAL_SCOPE = "all"
VALID_SCOPES = {GLOBAL_SCOPE, PROJECT_SCOPE}
VALID_RETRIEVAL_SCOPES = {
    DEFAULT_RETRIEVAL_SCOPE,
    GLOBAL_RETRIEVAL_SCOPE,
    PROJECT_RETRIEVAL_SCOPE,
    ALL_RETRIEVAL_SCOPE,
}


def normalize_project_root(project_root: Optional[Union[str, Path]] = None) -> str:
    """Resolve a project root using the host filesystem's path semantics."""
    root = Path(project_root or Path.cwd()).expanduser().resolve(strict=False)
    return os.path.normcase(os.path.normpath(str(root)))


def project_identity(project_root: Optional[Union[str, Path]] = None) -> Tuple[str, str]:
    """Return ``(opaque_id, display_label)`` without persisting the root path."""
    normalized_root = normalize_project_root(project_root)
    opaque_id = hashlib.sha256(normalized_root.encode("utf-8")).hexdigest()[:16]
    label = Path(normalized_root).name or normalized_root
    return opaque_id, label


def registered_project_identity(
    project_root: Optional[Union[str, Path]] = None,
    registry_path: Optional[Union[str, Path]] = None,
) -> Tuple[str, str]:
    """Resolve a stable identity through the local registry when available.

    The path-hash fallback is retained for callers that do not have a vault
    context (and for legacy records). Capture paths should pass a registry so
    moving or renaming a project does not silently create a new namespace.
    """
    if registry_path is None:
        return project_identity(project_root)
    from project_registry import ProjectRegistry

    record = ProjectRegistry(registry_path).register(project_root or Path.cwd())
    return record["project_id"], record["project_label"]


def legacy_project_id(project: str) -> str:
    """Create a stable compatibility ID when only an old label is available."""
    value = str(project or "").strip().lower()
    return f"legacy-{hashlib.sha256(value.encode('utf-8')).hexdigest()[:16]}"


def normalize_content(content: str) -> str:
    """Use the historical content normalization before hashing."""
    return " ".join(str(content).lower().split())


def scoped_fingerprint(
    content: str,
    scope: str = GLOBAL_SCOPE,
    project_id: str = "",
    type_: str = "",
) -> str:
    """Create a dedup key from scope, type, project namespace and content."""
    scope = scope or GLOBAL_SCOPE
    if scope not in VALID_SCOPES:
        raise ValueError(f"Unsupported memory scope: {scope}")
    if scope == PROJECT_SCOPE and not project_id:
        raise ValueError("project_id is required for project-scoped memory")
    namespace = f"{scope}:{project_id if scope == PROJECT_SCOPE else ''}"
    normalized_type = str(type_ or "").strip().lower()
    key = f"{namespace}\n{normalized_type}\n{normalize_content(content)}"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]


def legacy_content_fingerprint(content: str) -> str:
    """Return the pre-scope fingerprint for backward-compatible lookup."""
    return hashlib.sha256(normalize_content(content).encode("utf-8")).hexdigest()[:16]


def fingerprint_aliases(
    content: str,
    type_: str,
    scope: str = GLOBAL_SCOPE,
    project_id: str = "",
    include_legacy: bool = False,
) -> List[str]:
    """Return the current key plus explicitly-marked legacy lookup keys."""
    aliases = [scoped_fingerprint(content, scope, project_id, type_)]
    if include_legacy:
        aliases.append(scoped_fingerprint(content, scope, project_id))
        if scope == GLOBAL_SCOPE:
            aliases.append(legacy_content_fingerprint(content))
    return list(dict.fromkeys(aliases))


def infer_memory_scope(memory: Dict) -> Tuple[str, str, str]:
    """Normalize current and legacy records to ``(scope, project, id)``."""
    explicit_scope = memory.get("scope")
    project = str(memory.get("project_label") or memory.get("project") or "").strip()
    project_id = str(memory.get("project_id") or "").strip()

    if explicit_scope not in VALID_SCOPES:
        explicit_scope = PROJECT_SCOPE if project or project_id else GLOBAL_SCOPE

    if explicit_scope == GLOBAL_SCOPE:
        return GLOBAL_SCOPE, "", ""

    if not project_id and project:
        project_id = legacy_project_id(project)
    return PROJECT_SCOPE, project, project_id


def resolve_capture_scope(
    scope: Optional[str] = None,
    project: str = "",
    project_id: str = "",
    project_root: Optional[Union[str, Path]] = None,
    registry_path: Optional[Union[str, Path]] = None,
    default_to_project: bool = False,
) -> Tuple[str, str, str]:
    """Resolve caller input and enforce global/project invariants."""
    project = str(project or "").strip()
    project_id = str(project_id or "").strip()
    if scope is None:
        scope = PROJECT_SCOPE if (project or project_id or default_to_project) else GLOBAL_SCOPE
    if scope not in VALID_SCOPES:
        raise ValueError(f"scope must be one of: {', '.join(sorted(VALID_SCOPES))}")

    if scope == GLOBAL_SCOPE:
        if project or project_id:
            raise ValueError("global memory cannot carry project or project_id")
        return GLOBAL_SCOPE, "", ""

    if project_root is not None:
        derived_id, derived_label = registered_project_identity(project_root, registry_path)
        project_id = project_id or derived_id
        project = project or derived_label
    if not project_id:
        if project:
            project_id = legacy_project_id(project)
        else:
            raise ValueError("project_id or project_root is required for project scope")
    if not project:
        project = project_id
    return PROJECT_SCOPE, project, project_id


def filter_memories(
    memories: Iterable[Dict],
    project_id: Optional[str] = None,
    retrieval_scope: str = DEFAULT_RETRIEVAL_SCOPE,
) -> List[Dict]:
    """Apply the shared safe retrieval policy to memory records."""
    if retrieval_scope not in VALID_RETRIEVAL_SCOPES:
        raise ValueError(f"Unsupported retrieval scope: {retrieval_scope}")
    if retrieval_scope in {PROJECT_RETRIEVAL_SCOPE, ALL_RETRIEVAL_SCOPE} and not project_id:
        if retrieval_scope == PROJECT_RETRIEVAL_SCOPE:
            raise ValueError("project_id is required for project retrieval")

    filtered = []
    for memory in memories:
        scope, _, memory_project_id = infer_memory_scope(memory)
        if retrieval_scope == ALL_RETRIEVAL_SCOPE:
            filtered.append(memory)
        elif retrieval_scope == GLOBAL_RETRIEVAL_SCOPE:
            if scope == GLOBAL_SCOPE:
                filtered.append(memory)
        elif retrieval_scope == PROJECT_RETRIEVAL_SCOPE:
            if scope == PROJECT_SCOPE and memory_project_id == project_id:
                filtered.append(memory)
        elif scope == GLOBAL_SCOPE or (
            project_id and scope == PROJECT_SCOPE and memory_project_id == project_id
        ):
            filtered.append(memory)
    return filtered


def scope_sort_key(memory: Dict, project_id: Optional[str]) -> Tuple[int, float]:
    """Put current-project records ahead of global records within a result set."""
    scope, _, memory_project_id = infer_memory_scope(memory)
    current_first = 0 if project_id and scope == PROJECT_SCOPE and memory_project_id == project_id else 1
    return current_first, 0.0
