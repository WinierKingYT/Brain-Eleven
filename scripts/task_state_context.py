#!/usr/bin/env python3
"""Compatibility and direct-execution adapter for task/state composition."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from types import ModuleType


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _load_canonical(name: str) -> ModuleType:
    """Load and cache the canonical task/state context module."""
    module = sys.modules.get(name)
    if module is None:
        module = importlib.import_module(name)
    sys.modules.setdefault(name, module)
    return module


_canonical = _load_canonical("brain_eleven.runtime.task_state_context")

_COMPAT_NAMES = (
    "ROOT_IDENTITY_PATTERN",
    "ProjectLineageError",
    "registry_snapshot_for_root",
    "CurrentProjectState",
    "StateResolver",
    "TaskAnalyzer",
    "TaskEnvelope",
    "TaskProjectResolutionError",
    "TaskValidationError",
    "TASK_STATE_CONTEXT_SCHEMA_VERSION",
    "LINEAGE_STATUSES",
    "TaskStateLineageError",
    "TaskStateLineage",
    "TaskStateContext",
    "TaskStateComposer",
    "main",
)

for _name in _COMPAT_NAMES:
    globals()[_name] = getattr(_canonical, _name)

__all__ = [name for name in _COMPAT_NAMES if not name.startswith("_")]

if __name__ in {"scripts.task_state_context", "task_state_context"}:
    sys.modules.setdefault("task_state_context", sys.modules[__name__])
    sys.modules.setdefault("scripts.task_state_context", sys.modules[__name__])


if __name__ == "__main__":
    raise SystemExit(_canonical.main())
