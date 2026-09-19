#!/usr/bin/env python3
"""Compatibility/direct-execution adapter for the canonical project registry.

The implementation is owned by :mod:`brain_eleven.projects.registry`. This
module preserves the historical `scripts.project_registry` and bare
`project_registry` paths, including standalone copied-hook execution when a
repository root is discoverable.
"""

from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path


def _candidate_package_roots():
    candidates = [
        os.environ.get("BRAIN_ELEVEN_ROOT"),
        os.environ.get("BRAIN_ELEVEN_VAULT"),
        str(Path.cwd()),
        str(Path(__file__).resolve().parents[1]),
    ]
    seen = set()
    for raw in candidates:
        if not raw:
            continue
        try:
            current = Path(raw).expanduser().resolve(strict=False)
        except (OSError, RuntimeError):
            continue
        for root in (current, *current.parents):
            key = str(root)
            if key in seen:
                continue
            seen.add(key)
            if (root / "brain_eleven" / "projects" / "registry.py").is_file():
                yield root


for _root in _candidate_package_roots():
    if str(_root) not in sys.path:
        sys.path.insert(0, str(_root))
    break

# This explicit packaged import is also the dependency guard for callers that
# inspect the compatibility boundary statically.
from brain_eleven.infrastructure.locking import file_lock  # noqa: E402,F401
from brain_eleven.projects.registry import (  # noqa: E402,F401
    BACKUP_SCHEMA_VERSION,
    REGISTRY_BACKUP_FILENAME,
    REGISTRY_FILENAME,
    REGISTRY_SCHEMA_VERSION,
    VALID_STATUSES,
    ProjectRegistry,
    ProjectRegistryBackupError,
    ProjectRegistryConflict,
    ProjectRegistryError,
    main,
    normalize_registry_root,
    registry_backup_path,
    registry_path,
)

_CANONICAL = importlib.import_module("brain_eleven.projects.registry")

# Preserve module-level helpers used by legacy callers and failure-injection
# tests when this file is loaded under a copied or arbitrary module name.
for _name, _value in vars(_CANONICAL).items():
    if not _name.startswith("__"):
        globals().setdefault(_name, _value)

__all__ = getattr(_CANONICAL, "__all__", (
    "ProjectRegistry",
    "ProjectRegistryError",
    "ProjectRegistryConflict",
    "ProjectRegistryBackupError",
    "BACKUP_SCHEMA_VERSION",
    "REGISTRY_BACKUP_FILENAME",
    "REGISTRY_FILENAME",
    "REGISTRY_SCHEMA_VERSION",
    "VALID_STATUSES",
    "normalize_registry_root",
    "registry_backup_path",
    "registry_path",
    "main",
))

if __name__ in {"scripts.project_registry", "project_registry"}:
    # Keep the package, scripts, and bare import paths on one module object so
    # monkeypatches and exception identities remain truthful.
    sys.modules[__name__] = _CANONICAL
elif __name__ == "__main__":
    raise SystemExit(main())
