"""Stable package surface for typed extraction-to-state proposals."""

from __future__ import annotations

from brain_eleven._legacy import load_legacy_module


_legacy = load_legacy_module("state_boundary", "state_boundary.py")

BOUNDARY_SCHEMA_VERSION = _legacy.BOUNDARY_SCHEMA_VERSION
BOUNDARY_VERSION = _legacy.BOUNDARY_VERSION
BoundaryStatus = _legacy.BoundaryStatus
BoundaryResult = _legacy.BoundaryResult
StateBoundary = _legacy.StateBoundary

__all__ = [
    "BOUNDARY_SCHEMA_VERSION",
    "BOUNDARY_VERSION",
    "BoundaryStatus",
    "BoundaryResult",
    "StateBoundary",
]
