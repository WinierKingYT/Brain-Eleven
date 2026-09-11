#!/usr/bin/env python3
"""Compatibility/direct-execution adapter for scope-v2 migration."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from types import ModuleType

from brain_eleven.memory import MemoryStore as _PackageMemoryStore  # noqa: E402


_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def _load_canonical(name: str) -> ModuleType:
    """Load and cache the package implementation once."""

    existing = sys.modules.get(name)
    if existing is not None:
        return existing
    module = importlib.import_module(name)
    sys.modules.setdefault(name, module)
    return module


_migration = _load_canonical("brain_eleven.memory.migrations")

SCOPE_MIGRATION_NAME = _migration.SCOPE_MIGRATION_NAME
MIGRATION_NAME = SCOPE_MIGRATION_NAME
GLOBAL_SCOPE = _migration.GLOBAL_SCOPE
PROJECT_SCOPE = _migration.PROJECT_SCOPE
MemoryStore = _PackageMemoryStore
MemoryStoreCorrupt = _migration.MemoryStoreCorrupt
infer_memory_scope = _migration.infer_memory_scope
no_change = _migration.no_change
scoped_fingerprint = _migration.scoped_fingerprint
MemoryScopeMigrationError = _migration.MemoryScopeMigrationError
migrate_scope = _migration.migrate_scope
rollback_scope = _migration.rollback_scope
migrate = migrate_scope
rollback = rollback_scope
main = _migration.main

__all__ = [
    "SCOPE_MIGRATION_NAME",
    "MIGRATION_NAME",
    "GLOBAL_SCOPE",
    "PROJECT_SCOPE",
    "MemoryStore",
    "MemoryStoreCorrupt",
    "infer_memory_scope",
    "no_change",
    "scoped_fingerprint",
    "MemoryScopeMigrationError",
    "migrate_scope",
    "rollback_scope",
    "migrate",
    "rollback",
    "main",
]

# Preserve the historical bare module name used by pytest and direct imports.
if __name__ in {"scripts.migrate_memory_scope", "memory_scope_migration"}:
    sys.modules.setdefault("memory_scope_migration", _migration)


if __name__ == "__main__":
    raise SystemExit(main())
