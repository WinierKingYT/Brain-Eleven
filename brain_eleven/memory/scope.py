"""Stable package surface for canonical memory scope policy.

The scope implementation remains in ``scripts/memory_scope.py`` during the
strangler migration.  This adapter re-exports the exact same constants and
functions so retrieval callers share one policy without creating a second
scope implementation.
"""

from __future__ import annotations

from brain_eleven._legacy import load_legacy_module


_legacy = load_legacy_module("memory_scope", "memory_scope.py")

ALL_RETRIEVAL_SCOPE = _legacy.ALL_RETRIEVAL_SCOPE
DEFAULT_RETRIEVAL_SCOPE = _legacy.DEFAULT_RETRIEVAL_SCOPE
GLOBAL_RETRIEVAL_SCOPE = _legacy.GLOBAL_RETRIEVAL_SCOPE
GLOBAL_SCOPE = _legacy.GLOBAL_SCOPE
PROJECT_RETRIEVAL_SCOPE = _legacy.PROJECT_RETRIEVAL_SCOPE
PROJECT_SCOPE = _legacy.PROJECT_SCOPE
VALID_RETRIEVAL_SCOPES = _legacy.VALID_RETRIEVAL_SCOPES
VALID_SCOPES = _legacy.VALID_SCOPES

filter_memories = _legacy.filter_memories
fingerprint_aliases = _legacy.fingerprint_aliases
infer_memory_scope = _legacy.infer_memory_scope
legacy_content_fingerprint = _legacy.legacy_content_fingerprint
legacy_project_id = _legacy.legacy_project_id
normalize_content = _legacy.normalize_content
normalize_project_root = _legacy.normalize_project_root
project_identity = _legacy.project_identity
registered_project_identity = _legacy.registered_project_identity
resolve_capture_scope = _legacy.resolve_capture_scope
resolve_retrieval_project = _legacy.resolve_retrieval_project
resolved_project_identity = _legacy.resolved_project_identity
scope_sort_key = _legacy.scope_sort_key
scoped_fingerprint = _legacy.scoped_fingerprint

__all__ = [
    "ALL_RETRIEVAL_SCOPE",
    "DEFAULT_RETRIEVAL_SCOPE",
    "GLOBAL_RETRIEVAL_SCOPE",
    "GLOBAL_SCOPE",
    "PROJECT_RETRIEVAL_SCOPE",
    "PROJECT_SCOPE",
    "VALID_RETRIEVAL_SCOPES",
    "VALID_SCOPES",
    "filter_memories",
    "fingerprint_aliases",
    "infer_memory_scope",
    "legacy_content_fingerprint",
    "legacy_project_id",
    "normalize_content",
    "normalize_project_root",
    "project_identity",
    "registered_project_identity",
    "resolve_capture_scope",
    "resolve_retrieval_project",
    "resolved_project_identity",
    "scope_sort_key",
    "scoped_fingerprint",
]
