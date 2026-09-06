"""Small compatibility loader for legacy script implementations.

The repository consolidation keeps the existing ``scripts`` modules as the
backing implementation for now.  Loading them through one cached helper
prevents package callers from creating a second class/module identity while
the strangler migration is in progress.
"""

from __future__ import annotations

import importlib.util
import sys
from functools import lru_cache
from pathlib import Path
from types import ModuleType


_ROOT = Path(__file__).resolve().parents[1]
_SCRIPTS = _ROOT / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))


@lru_cache(maxsize=None)
def load_legacy_module(module_name: str, filename: str) -> ModuleType:
    """Load one legacy script once under a stable module name."""

    script_path = (_SCRIPTS / filename).resolve()
    if not script_path.is_file():
        raise ImportError(f"legacy implementation not found: {filename}")

    existing = sys.modules.get(module_name)
    if existing is not None:
        existing_path = getattr(existing, "__file__", None)
        if existing_path and Path(existing_path).resolve() == script_path:
            return existing

    spec = importlib.util.spec_from_file_location(module_name, script_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"could not load legacy implementation: {filename}")

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(module_name, None)
        raise
    return module
