#!/usr/bin/env python3
"""Compatibility adapter for the canonical support cache implementation."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType


_ROOT = Path(__file__).resolve().parents[1]


def _load_canonical(name: str, path: Path) -> ModuleType:
    """Load a canonical support module once for old script entrypoints."""

    existing = sys.modules.get(name)
    if existing is not None:
        return existing

    specification = importlib.util.spec_from_file_location(name, path)
    if specification is None or specification.loader is None:
        raise ImportError(f"Cannot load canonical module: {path}")

    module = importlib.util.module_from_spec(specification)
    sys.modules[name] = module
    try:
        specification.loader.exec_module(module)
    except Exception:
        sys.modules.pop(name, None)
        raise
    return module


_load_canonical(
    "brain_eleven.support.logging",
    _ROOT / "brain_eleven" / "support" / "logging.py",
)
_cache = _load_canonical(
    "brain_eleven.support.cache",
    _ROOT / "brain_eleven" / "support" / "cache.py",
)

CacheManager = _cache.CacheManager
DiskCache = _cache.DiskCache
LRUCache = _cache.LRUCache
REDIS_AVAILABLE = _cache.REDIS_AVAILABLE
logger = _cache.logger

__all__ = ["CacheManager", "DiskCache", "LRUCache", "REDIS_AVAILABLE", "logger"]

# Keep the historical bare import name available for callers that imported
# the script before the package migration.
if __name__ == "scripts.cache_manager":
    sys.modules.setdefault("cache_manager", sys.modules[__name__])


if __name__ == "__main__":
    cache = CacheManager(vault_path=".")

    cache.set("test:key1", {"foo": "bar"})
    print("get test:key1 ->", cache.get("test:key1"))

    calls = {"n": 0}

    def expensive():
        calls["n"] += 1
        return {"computed": True, "call_count": calls["n"]}

    r1 = cache.get_or_compute("test:computed", expensive)
    r2 = cache.get_or_compute("test:computed", expensive)
    print("r1 ==", r1)
    print("r2 ==", r2)
    print("compute calls (should be 1):", calls["n"])

    print("\nCache stats:", json.dumps(cache.stats(), indent=2))

    cache.delete("test:key1")
    cache.delete("test:computed")
