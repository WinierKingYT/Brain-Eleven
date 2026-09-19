#!/usr/bin/env python3
"""Compatibility/direct-execution adapter for the canonical memory store.

The implementation is owned by brain_eleven.memory.store. This module
preserves the historical scripts.memory_store and bare memory_store import
paths without creating a second store authority.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path


_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    # Historical direct execution starts with scripts/ on sys.path.
    sys.path.insert(0, str(_ROOT))

from brain_eleven.infrastructure.locking import MemoryStoreLockTimeout  # noqa: E402,F401
from brain_eleven.memory.store import (  # noqa: E402,F401
    CANONICAL_SCHEMA_VERSION,
    MemoryStore,
    MemoryStoreConflict,
    MemoryStoreCorrupt,
    MemoryStoreError,
    MemoryStoreRecordInvalid,
    _fsync_parent_directory,
    no_change,
)

__all__ = [
    "CANONICAL_SCHEMA_VERSION",
    "MemoryStore",
    "MemoryStoreConflict",
    "MemoryStoreCorrupt",
    "MemoryStoreError",
    "MemoryStoreRecordInvalid",
    "no_change",
]
