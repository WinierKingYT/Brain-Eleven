"""Package boundary for the canonical vault-local project registry.

This is the first PRE-12 strangler step.  The implementation remains in the
legacy module until parity coverage is complete; this package is the stable
import surface for new code.  It deliberately exposes the exact same class
and helper objects, so identity, lifecycle, and storage semantics cannot
drift during consolidation.
"""

from __future__ import annotations

from scripts.project_registry import (
    REGISTRY_FILENAME,
    REGISTRY_SCHEMA_VERSION,
    VALID_STATUSES,
    ProjectRegistry,
    ProjectRegistryError,
    normalize_registry_root,
    registry_path,
)

__all__ = [
    "ProjectRegistry",
    "ProjectRegistryError",
    "REGISTRY_FILENAME",
    "REGISTRY_SCHEMA_VERSION",
    "VALID_STATUSES",
    "normalize_registry_root",
    "registry_path",
]
