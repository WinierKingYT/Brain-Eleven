"""Package boundary for the canonical vault-local project registry.

This is the first PRE-12 strangler step.  The implementation remains in the
legacy module until parity coverage is complete; this package is the stable
import surface for new code.  It deliberately exposes the exact same class
and helper objects, so identity, lifecycle, and storage semantics cannot
drift during consolidation.
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_SCRIPTS = _ROOT / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

# Import the established implementation without importing the ``scripts``
# package (whose historical __init__ eagerly loads legacy entry points).
from project_registry import (  # noqa: E402
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
