"""Stable package surface for the metadata-first memory truth engine.

The implementation remains in the legacy script during the strangler
migration.  Loading it through the shared compatibility loader preserves the
same class and enum identities for package and legacy callers.
"""

from __future__ import annotations

from brain_eleven._legacy import load_legacy_module


_legacy = load_legacy_module("memory_truth", "memory_truth.py")

TruthError = _legacy.TruthError
TruthInputError = _legacy.TruthInputError
TruthCorruptError = _legacy.TruthCorruptError
TruthAction = _legacy.TruthAction
TruthStatus = _legacy.TruthStatus
TruthCandidate = _legacy.TruthCandidate
TruthDecision = _legacy.TruthDecision
TruthResult = _legacy.TruthResult
MemoryTruthEngine = _legacy.MemoryTruthEngine
main = _legacy.main

__all__ = [
    "TruthError",
    "TruthInputError",
    "TruthCorruptError",
    "TruthAction",
    "TruthStatus",
    "TruthCandidate",
    "TruthDecision",
    "TruthResult",
    "MemoryTruthEngine",
    "main",
]
