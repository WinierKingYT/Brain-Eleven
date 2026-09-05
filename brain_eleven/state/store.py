"""Stable package boundary for the canonical project state store.

The Phase 16 implementation is still owned by ``scripts/state_store.py``.
This module exposes that implementation through the consolidated package
namespace while preserving object identity and fail-closed semantics.
"""

from __future__ import annotations

import sys
from pathlib import Path


_ROOT = Path(__file__).resolve().parents[2]
_SCRIPTS = _ROOT / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from state_store import (  # noqa: E402
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
