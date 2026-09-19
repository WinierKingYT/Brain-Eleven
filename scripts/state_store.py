#!/usr/bin/env python3
"""Compatibility adapter for the canonical project state store.

The implementation is owned by :mod:`brain_eleven.state.store`. This module
preserves the historical `scripts.state_store` and bare `state_store`
import paths while keeping module-level monkeypatches on the canonical
implementation.
"""

from __future__ import annotations

import sys
from importlib import import_module
from pathlib import Path

from brain_eleven.infrastructure.locking import (  # noqa: E402,F401
    MemoryStoreLockTimeout,
    file_lock,
    memory_store_lock,
)
from brain_eleven.memory import MemoryStore, MemoryStoreError  # noqa: E402,F401
from brain_eleven.projects.registry import ProjectRegistry, ProjectRegistryError  # noqa: E402,F401

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    # Historical direct execution starts with scripts/ on sys.path.
    sys.path.insert(0, str(_ROOT))

if __name__ != "__main__":
    _canonical = import_module("brain_eleven.state.store")
    # Make scripts.state_store and bare state_store resolve to the canonical
    # module object, so monkeypatches and exception identities remain truthful.
    sys.modules[__name__] = _canonical
