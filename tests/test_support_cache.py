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


def test_package_and_legacy_cache_objects_share_identity() -> None:
    legacy = importlib.import_module("scripts.cache_manager")
    bare_legacy = importlib.import_module("cache_manager")

    assert PackagedCacheManager is CacheManager is legacy.CacheManager
    assert PackagedDiskCache is DiskCache is legacy.DiskCache
    assert PackagedLRUCache is LRUCache is legacy.LRUCache
    assert legacy.REDIS_AVAILABLE is bare_legacy.REDIS_AVAILABLE


def test_legacy_cache_file_is_only_an_adapter() -> None:
    source_path = ROOT / "scripts" / "cache_manager.py"
    source = source_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    defined_classes = {
        node.name for node in ast.walk(tree) if isinstance(node, ast.ClassDef)
    }

    assert "brain_eleven.support.cache" in source
    assert not defined_classes & {"LRUCache", "DiskCache", "CacheManager"}
    assert not any(
        isinstance(node, ast.FunctionDef)
        and node.name in {"get", "set", "delete", "clear", "get_or_compute"}
        for node in ast.walk(tree)
    )


def test_package_and_legacy_imports_have_matching_cache_behavior(tmp_path: Path) -> None:
    package_lru = LRUCache(max_size=2, ttl_seconds=60)
    legacy = importlib.import_module("scripts.cache_manager")
    legacy_lru = legacy.LRUCache(max_size=2, ttl_seconds=60)

    for cache in (package_lru, legacy_lru):
        cache.set("a", 1)
        cache.set("b", 2)
        cache.get("a")
        cache.set("c", 3)

    assert package_lru.get("b") == legacy_lru.get("b") is None
    assert package_lru.get("a") == legacy_lru.get("a") == 1
    assert package_lru.get("c") == legacy_lru.get("c") == 3

    package_disk = DiskCache(str(tmp_path / "package"), ttl_seconds=60)
    legacy_disk = legacy.DiskCache(str(tmp_path / "legacy"), ttl_seconds=60)
    package_disk.set("same", {"value": 1})
    legacy_disk.set("same", {"value": 1})
    assert package_disk.get("same") == legacy_disk.get("same") == {"value": 1}


def test_direct_execution_preserves_cache_demo_contract(tmp_path: Path) -> None:
    script = ROOT / "scripts" / "cache_manager.py"
    result = subprocess.run(
        [sys.executable, str(script)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "get test:key1 -> {'foo': 'bar'}" in result.stdout
    assert "compute calls (should be 1): 1" in result.stdout
    assert "Cache stats:" in result.stdout
