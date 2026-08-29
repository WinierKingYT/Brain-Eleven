#!/usr/bin/env python3
"""
Brain-Eleven v3 - Multi-Level Cache Manager (Phase 9A)

L1: In-memory LRU cache (fastest, per-process, small)
L2: Redis cache (shared across processes, network hop)
L3: Disk fallback (JSON file, survives restarts, slowest)

Read path:  L1 -> L2 -> L3 -> miss (caller computes, then backfills all levels)
Write path: write-through to all configured levels
"""

import json
import time
import hashlib
import socket
from collections import OrderedDict
from pathlib import Path
from typing import Any, Optional
import threading

from logging_config import setup_logging

logger = setup_logging(__name__)

try:
    import redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    logger.warning("redis package not installed - L2 cache disabled")


class LRUCache:
    """Thread-safe in-memory LRU cache (L1)"""

    def __init__(self, max_size: int = 500, ttl_seconds: int = 300):
        self.max_size = max_size
        self.ttl_seconds = ttl_seconds
        self._store: "OrderedDict[str, tuple[Any, float]]" = OrderedDict()
        self._lock = threading.Lock()
        self.hits = 0
        self.misses = 0

    def get(self, key: str) -> Optional[Any]:
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                self.misses += 1
                return None

            value, expires_at = entry
            if time.time() > expires_at:
                del self._store[key]
                self.misses += 1
                return None

            # Move to end (most recently used)
            self._store.move_to_end(key)
            self.hits += 1
            return value

    def set(self, key: str, value: Any) -> None:
        with self._lock:
            expires_at = time.time() + self.ttl_seconds
            self._store[key] = (value, expires_at)
            self._store.move_to_end(key)

            while len(self._store) > self.max_size:
                self._store.popitem(last=False)

    def delete(self, key: str) -> None:
        with self._lock:
            self._store.pop(key, None)

    def clear(self) -> None:
        with self._lock:
            self._store.clear()

    def stats(self) -> dict:
        total = self.hits + self.misses
        return {
            "size": len(self._store),
            "max_size": self.max_size,
            "hits": self.hits,
            "misses": self.misses,
            "hit_rate": round(self.hits / total, 4) if total else 0.0,
        }


class DiskCache:
    """JSON file-backed fallback cache (L3)"""

    def __init__(self, cache_dir: str = "cache", ttl_seconds: int = 3600):
        self.cache_path = Path(cache_dir)
        self.cache_path.mkdir(exist_ok=True)
        self.ttl_seconds = ttl_seconds
        self._lock = threading.Lock()

    def _file_for(self, key: str) -> Path:
        digest = hashlib.sha256(key.encode()).hexdigest()
        return self.cache_path / f"{digest}.json"

    def get(self, key: str) -> Optional[Any]:
        path = self._file_for(key)
        if not path.exists():
            return None

        try:
            with self._lock, open(path) as f:
                record = json.load(f)

            if time.time() > record["expires_at"]:
                path.unlink(missing_ok=True)
                return None

            return record["value"]
        except (json.JSONDecodeError, KeyError, OSError) as e:
            logger.warning(f"Disk cache read error for key {key}: {e}")
            return None

    def set(self, key: str, value: Any) -> None:
        path = self._file_for(key)
        record = {
            "key": key,
            "value": value,
            "expires_at": time.time() + self.ttl_seconds,
        }
        try:
            with self._lock:
                tmp_path = path.with_suffix(".tmp")
                with open(tmp_path, "w") as f:
                    json.dump(record, f)
                tmp_path.replace(path)
        except OSError as e:
            logger.warning(f"Disk cache write error for key {key}: {e}")

    def delete(self, key: str) -> None:
        self._file_for(key).unlink(missing_ok=True)

    def clear(self) -> None:
        for f in self.cache_path.glob("*.json"):
            f.unlink(missing_ok=True)


class CacheManager:
    """
    Unified multi-level cache facade.

    Usage:
        cache = CacheManager(vault_path)
        result = cache.get_or_compute("search:foo", lambda: expensive_search("foo"))
    """

    def __init__(
        self,
        vault_path: str = ".",
        redis_host: str = "localhost",
        redis_port: int = 6379,
        l1_max_size: int = 500,
        l1_ttl: int = 300,
        l2_ttl: int = 1800,
        l3_ttl: int = 3600,
        enable_l2: bool = True,
    ):
        self.vault_path = Path(vault_path)
        self.l1 = LRUCache(max_size=l1_max_size, ttl_seconds=l1_ttl)
        self.l3 = DiskCache(cache_dir=str(self.vault_path / "cache"), ttl_seconds=l3_ttl)
        self.l2_ttl = l2_ttl

        self.redis_client = None
        if enable_l2 and REDIS_AVAILABLE and not self._tcp_reachable(redis_host, redis_port):
            logger.warning(
                f"L2 Redis unreachable at {redis_host}:{redis_port} (TCP pre-check failed), "
                "falling back to L1+L3 only"
            )
        elif enable_l2 and REDIS_AVAILABLE:
            try:
                self.redis_client = redis.Redis(
                    host=redis_host, port=redis_port, decode_responses=True,
                    socket_connect_timeout=2, socket_timeout=2,
                )
                self.redis_client.ping()
                logger.info(f"✅ L2 Redis cache connected ({redis_host}:{redis_port})")
            except (redis.exceptions.RedisError, ConnectionError) as e:
                logger.warning(f"L2 Redis unavailable, falling back to L1+L3 only: {e}")
                self.redis_client = None

    @staticmethod
    def _tcp_reachable(host: str, port: int, timeout: float = 1.0) -> bool:
        """
        Fast TCP-level pre-check before handing off to redis-py.

        On some platforms (notably Windows) an unreachable/refused host can
        make the OS-level connect take far longer than the timeout passed to
        redis-py, stalling startup for 15-20s. A raw socket with an enforced
        timeout fails fast and lets callers skip Redis immediately instead.
        """
        try:
            with socket.create_connection((host, port), timeout=timeout):
                return True
        except OSError:
            return False

    # -- internal helpers -------------------------------------------------

    def _l2_get(self, key: str) -> Optional[Any]:
        if not self.redis_client:
            return None
        try:
            raw = self.redis_client.get(key)
            return json.loads(raw) if raw is not None else None
        except (redis.exceptions.RedisError, json.JSONDecodeError) as e:
            logger.warning(f"L2 read error for key {key}: {e}")
            return None

    def _l2_set(self, key: str, value: Any) -> None:
        if not self.redis_client:
            return
        try:
            self.redis_client.setex(key, self.l2_ttl, json.dumps(value))
        except redis.exceptions.RedisError as e:
            logger.warning(f"L2 write error for key {key}: {e}")

    def _l2_delete(self, key: str) -> None:
        if not self.redis_client:
            return
        try:
            self.redis_client.delete(key)
        except redis.exceptions.RedisError as e:
            logger.warning(f"L2 delete error for key {key}: {e}")

    # -- public API ---------------------------------------------------------

    def get(self, key: str) -> Optional[Any]:
        """Read through L1 -> L2 -> L3, backfilling higher levels on hit."""
        value = self.l1.get(key)
        if value is not None:
            return value

        value = self._l2_get(key)
        if value is not None:
            self.l1.set(key, value)
            return value

        value = self.l3.get(key)
        if value is not None:
            self.l1.set(key, value)
            self._l2_set(key, value)
            return value

        return None

    def set(self, key: str, value: Any) -> None:
        """Write-through to every configured cache level."""
        self.l1.set(key, value)
        self._l2_set(key, value)
        self.l3.set(key, value)

    def delete(self, key: str) -> None:
        self.l1.delete(key)
        self._l2_delete(key)
        self.l3.delete(key)

    def clear(self) -> None:
        self.l1.clear()
        self.l3.clear()
        if self.redis_client:
            try:
                self.redis_client.flushdb()
            except redis.exceptions.RedisError as e:
                logger.warning(f"L2 clear error: {e}")

    def get_or_compute(self, key: str, compute_fn, *args, **kwargs) -> Any:
        """Return cached value, or compute, cache, and return it."""
        cached = self.get(key)
        if cached is not None:
            return cached

        value = compute_fn(*args, **kwargs)
        self.set(key, value)
        return value

    @staticmethod
    def make_key(*parts: str) -> str:
        """Build a stable cache key from arbitrary parts."""
        raw = "|".join(str(p) for p in parts)
        return hashlib.sha256(raw.encode()).hexdigest()[:32]

    def stats(self) -> dict:
        return {
            "l1": self.l1.stats(),
            "l2_connected": self.redis_client is not None,
            "l3_path": str(self.l3.cache_path),
        }


if __name__ == "__main__":
    cache = CacheManager(vault_path=".")

    # Basic set/get
    cache.set("test:key1", {"foo": "bar"})
    print("get test:key1 ->", cache.get("test:key1"))

    # get_or_compute
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
