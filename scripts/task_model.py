#!/usr/bin/env python3
"""Compatibility and direct-execution adapter for the task package contract."""

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
    """Load and cache one canonical package module."""
    module = sys.modules.get(name)
    if module is None:
        module = importlib.import_module(name)
    sys.modules.setdefault(name, module)
    return module


_canonical = _load_canonical("brain_eleven.runtime.task")

# Keep the historical surface, including registry names imported by older
# callers, while retaining one implementation authority in the package.
_COMPAT_NAMES = (
    "ProjectRegistry",
    "ProjectRegistryError",
    "TASK_SCHEMA_VERSION",
    "TASK_ID_PREFIX",
    "TASK_LIFECYCLES",
    "PROJECT_RESOLUTION_STATUSES",
    "INTENTS",
    "OPERATIONS",
    "RISK_LEVELS",
    "REQUESTED_OUTPUTS",
    "EVIDENCE_SOURCES",
    "MAX_REQUEST_CHARS",
    "TaskValidationError",
    "TaskProjectResolutionError",
    "TaskAnalyzer",
    "Evidence",
    "ProjectResolution",
    "TaskEnvelope",
    "utc_now",
    "new_task_id",
    "resolve_project",
    "validate_task",
    "render_task_json",
    "main",
    "_CROCKFORD",
    "_Rule",
    "_INTENT_RULES",
    "_DOMAIN_RULES",
    "_EXPLICIT_CONSTRAINT_RULES",
    "_RISK_RULES",
    "_INTENT_OPERATION",
    "_INTENT_OUTPUT",
    "_encode_crockford",
    "_normalized_request",
    "_matches_phrase",
    "_first_rule_value",
    "_all_rule_values",
    "_rule_confidence",
    "_extract_entities",
    "_risk_level",
    "_context_needs",
    "_require_string",
    "_require_confidence",
    "_require_string_tuple",
    "_mapping",
    "_exact_keys",
    "_human_summary",
)

for _name in _COMPAT_NAMES:
    globals()[_name] = getattr(_canonical, _name)

__all__ = [name for name in _COMPAT_NAMES if not name.startswith("_")]

if __name__ in {"scripts.task_model", "task_model"}:
    sys.modules.setdefault("task_model", sys.modules[__name__])


if __name__ == "__main__":
    raise SystemExit(_canonical.main())
