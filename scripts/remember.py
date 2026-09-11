#!/usr/bin/env python3
"""Compatibility and direct-execution adapter for canonical memory capture."""

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
    """Load and cache the package implementation under its canonical name."""
    module = sys.modules.get(name)
    if module is None:
        module = importlib.import_module(name)
    sys.modules.setdefault(name, module)
    return module


_capture = _load_canonical("brain_eleven.memory.capture")

GLOBAL_SCOPE = _capture.GLOBAL_SCOPE
PROJECT_SCOPE = _capture.PROJECT_SCOPE
DEFAULT_VAULT = _capture.DEFAULT_VAULT
MemoryValidator = _capture.MemoryValidator
EntityExtractor = _capture.EntityExtractor
CaptureSafetyError = _capture.CaptureSafetyError
CaptureSafetyResult = _capture.CaptureSafetyResult
evaluate_capture = _capture.evaluate_capture
require_safe_capture = _capture.require_safe_capture
default_vault_path = _capture.default_vault_path
default_project_id = _capture.default_project_id
is_project_opted_in = _capture.is_project_opted_in
proactive_capture_policy = _capture.proactive_capture_policy
remember = _capture.remember
main = _capture.main

__all__ = [
    "GLOBAL_SCOPE",
    "PROJECT_SCOPE",
    "DEFAULT_VAULT",
    "MemoryValidator",
    "EntityExtractor",
    "CaptureSafetyError",
    "CaptureSafetyResult",
    "evaluate_capture",
    "require_safe_capture",
    "default_vault_path",
    "default_project_id",
    "is_project_opted_in",
    "proactive_capture_policy",
    "remember",
    "main",
]

# Historical bare-module imports (``import remember``) resolve to this
# adapter in the test/runtime bootstrap.  The functions still originate from
# the canonical package module, so object identity is preserved.
if __name__ in {"scripts.remember", "remember"}:
    sys.modules.setdefault("remember", sys.modules[__name__])


if __name__ == "__main__":
    raise SystemExit(main())
