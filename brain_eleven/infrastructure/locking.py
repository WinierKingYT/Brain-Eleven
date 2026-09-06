"""Identity-preserving package surface for the repository file-lock policy.

PRE-12 keeps the existing cross-platform implementation in
``scripts/memory_store_lock.py`` while callers migrate to this stable package
namespace. No lock semantics, timeout behavior, or persistence ownership is
implemented here.
"""

from __future__ import annotations

from brain_eleven._legacy import load_legacy_module


_legacy = load_legacy_module("memory_store_lock", "memory_store_lock.py")

MemoryStoreLockTimeout = _legacy.MemoryStoreLockTimeout
file_lock = _legacy.file_lock
memory_store_lock = _legacy.memory_store_lock

__all__ = ["MemoryStoreLockTimeout", "file_lock", "memory_store_lock"]
