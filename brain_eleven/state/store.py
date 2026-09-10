"""Stable package boundary for the canonical project state store.

The Phase 16 implementation is still owned by ``scripts/state_store.py``.
This module exposes that implementation through the consolidated package
namespace while preserving object identity and fail-closed semantics.
"""

from __future__ import annotations

from scripts.state_store import (
    BLOCKER_STATUSES,
    CANONICAL_SOURCE_TYPES,
    MAX_AUDIT_EVENTS,
    MILESTONE_STATUSES,
    REQUIREMENT_STATUSES,
    SEVERITIES,
    STATE_FILENAME,
    STATE_SCHEMA_VERSION,
    STATE_SOURCE_TYPES,
    WORK_ITEM_STATUSES,
    StateError,
    StateProjectArchived,
    StateProjectUnknown,
    StateProvenanceError,
    StateReferenceError,
    StateSchemaError,
    StateStore,
    StateStoreConflict,
    StateStoreCorrupt,
    StateStoreLockTimeout,
    StateStorePersistenceError,
    StateTransitionError,
    StateService,
    empty_project_state,
    empty_state_document,
    new_state_id,
    state_store_path,
    utc_now,
    validate_state_document,
)

__all__ = [
    "BLOCKER_STATUSES",
    "CANONICAL_SOURCE_TYPES",
    "MAX_AUDIT_EVENTS",
    "MILESTONE_STATUSES",
    "REQUIREMENT_STATUSES",
    "SEVERITIES",
    "STATE_FILENAME",
    "STATE_SCHEMA_VERSION",
    "STATE_SOURCE_TYPES",
    "WORK_ITEM_STATUSES",
    "StateError",
    "StateProjectArchived",
    "StateProjectUnknown",
    "StateProvenanceError",
    "StateReferenceError",
    "StateSchemaError",
    "StateStore",
    "StateStoreConflict",
    "StateStoreCorrupt",
    "StateStoreLockTimeout",
    "StateStorePersistenceError",
    "StateTransitionError",
    "StateService",
    "empty_project_state",
    "empty_state_document",
    "new_state_id",
    "state_store_path",
    "utc_now",
    "validate_state_document",
]
