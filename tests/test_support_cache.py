"""Contract and parity tests for the IG-07 cache migration."""

from __future__ import annotations

import ast
import importlib
import subprocess
import sys
from pathlib import Path

from brain_eleven.support import (
    CacheManager as PackagedCacheManager,
    DiskCache as PackagedDiskCache,
    LRUCache as PackagedLRUCache,
)
from brain_eleven.support.cache import (
    CacheManager,
    DiskCache,
    LRUCache,
)


ROOT = Path(__file__).resolve().parents[1]


def test_package_exports_share_identity() -> None:
    assert PackagedCacheManager is CacheManager
    assert PackagedDiskCache is DiskCache
    assert PackagedLRUCache is LRUCache


def test_lru_eviction_and_disk_round_trip(tmp_path: Path) -> None:
    lru = LRUCache(max_size=2, ttl_seconds=60)
    lru.set("a", 1)
    lru.set("b", 2)
    lru.get("a")
    lru.set("c", 3)

    assert lru.get("b") is None
    assert lru.get("a") == 1
    assert lru.get("c") == 3

    disk = DiskCache(str(tmp_path / "disk"), ttl_seconds=60)
    disk.set("same", {"value": 1})
    assert disk.get("same") == {"value": 1}
