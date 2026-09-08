"""Importable namespace for the repository's legacy script modules.

Underscore-named modules are regular package modules. A small lazy loader
keeps the historical hyphenated modules available to callers that import them
through ``scripts`` without importing every legacy CLI as a package side
effect.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType


_SCRIPT_ROOT = Path(__file__).parent
_LEGACY_FILES = {
    "memory_compiler": "memory-compiler.py",
    "memory_validator": "memory-validator.py",
    "memory_lifecycle": "memory-lifecycle.py",
}


def _load_legacy_module(module_name: str) -> ModuleType:
    filename = _LEGACY_FILES[module_name]
    script_path = _SCRIPT_ROOT / filename
    qualified_name = f"{__name__}.{module_name}"
    existing = sys.modules.get(qualified_name) or sys.modules.get(module_name)
    if existing is not None:
        return existing
    specification = importlib.util.spec_from_file_location(qualified_name, script_path)
    if specification is None or specification.loader is None:
        raise ImportError(f"Cannot load legacy script module: {filename}")
    module = importlib.util.module_from_spec(specification)
    sys.modules[qualified_name] = module
    sys.modules[module_name] = module
    try:
        specification.loader.exec_module(module)
    except Exception:
        sys.modules.pop(qualified_name, None)
        sys.modules.pop(module_name, None)
        raise
    return module


def __getattr__(name: str) -> ModuleType:
    if name not in _LEGACY_FILES:
        raise AttributeError(name)
    return _load_legacy_module(name)


__all__ = tuple(_LEGACY_FILES)
