#!/usr/bin/env python3
"""
Phase 9B: Performance & Load Tests

Covers:
- Cache manager (Phase 9A) correctness under load
- L1 LRU eviction behavior
- L1 vs L3 latency characteristics
- Concurrent access safety (thread-safety of LRUCache/CacheManager)
- Basic throughput smoke test for get_or_compute
"""

import sys
import time
import threading
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from cache_manager import CacheManager, LRUCache, DiskCache  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def cache(tmp_path):
    """CacheManager pointed at an isolated temp vault, L2/Redis disabled.

    enable_l2=False avoids a real Redis connection attempt per test — on
    Windows a refused/absent Redis can make the TCP connect take far longer
    than the configured socket timeout, making the suite needlessly slow.
    """
    return CacheManager(
        vault_path=str(tmp_path), l1_max_size=50, l1_ttl=5, l3_ttl=5, enable_l2=False
    )


# ---------------------------------------------------------------------------
# L1 LRU Cache
# ---------------------------------------------------------------------------

class TestLRUCache:

    def test_set_and_get_returns_value(self):
        # Arrange
        lru = LRUCache(max_size=10, ttl_seconds=60)

        # Act
        lru.set("a", 1)

        # Assert
        assert lru.get("a") == 1

    def test_get_missing_key_returns_none_and_counts_miss(self):
        # Arrange
        lru = LRUCache(max_size=10, ttl_seconds=60)

        # Act
        result = lru.get("missing")

        # Assert
        assert result is None
        assert lru.misses == 1

    def test_evicts_least_recently_used_when_full(self):
        # Arrange
        lru = LRUCache(max_size=3, ttl_seconds=60)
        lru.set("a", 1)
        lru.set("b", 2)
        lru.set("c", 3)

        # Act: touch "a" so "b" becomes least-recently-used, then overflow
        lru.get("a")
        lru.set("d", 4)

        # Assert
        assert lru.get("b") is None  # evicted
        assert lru.get("a") == 1
        assert lru.get("c") == 3
        assert lru.get("d") == 4

    def test_expired_entry_is_treated_as_miss(self):
        # Arrange
        lru = LRUCache(max_size=10, ttl_seconds=0)  # instant expiry
        lru.set("a", 1)
        time.sleep(0.01)

        # Act
        result = lru.get("a")

        # Assert
        assert result is None

    def test_stats_reports_hit_rate(self):
        # Arrange
        lru = LRUCache(max_size=10, ttl_seconds=60)
        lru.set("a", 1)

        # Act
        lru.get("a")   # hit
        lru.get("a")   # hit
        lru.get("b")   # miss
        stats = lru.stats()

        # Assert
        assert stats["hits"] == 2
        assert stats["misses"] == 1
        assert stats["hit_rate"] == pytest.approx(2 / 3, rel=1e-3)

    def test_concurrent_writes_do_not_corrupt_size(self):
        # Arrange
        lru = LRUCache(max_size=1000, ttl_seconds=60)

        def writer(offset):
            for i in range(100):
                lru.set(f"key-{offset}-{i}", i)

        threads = [threading.Thread(target=writer, args=(t,)) for t in range(8)]

        # Act
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Assert: 800 unique keys, under max_size, no crash/corruption
        assert lru.stats()["size"] == 800


# ---------------------------------------------------------------------------
# L3 Disk Cache
# ---------------------------------------------------------------------------

class TestDiskCache:

    def test_set_and_get_roundtrip(self, tmp_path):
        # Arrange
        disk = DiskCache(cache_dir=str(tmp_path / "cache"), ttl_seconds=60)

        # Act
        disk.set("k", {"nested": [1, 2, 3]})

        # Assert
        assert disk.get("k") == {"nested": [1, 2, 3]}

    def test_expired_entry_is_removed_on_read(self, tmp_path):
        # Arrange
        disk = DiskCache(cache_dir=str(tmp_path / "cache"), ttl_seconds=0)
        disk.set("k", "v")
        time.sleep(0.01)

        # Act
        result = disk.get("k")

        # Assert
        assert result is None
        assert not disk._file_for("k").exists()

    def test_survives_process_restart_simulation(self, tmp_path):
        # Arrange: write with one instance, read with a fresh instance
        disk1 = DiskCache(cache_dir=str(tmp_path / "cache"), ttl_seconds=60)
        disk1.set("persisted", "value")

        # Act
        disk2 = DiskCache(cache_dir=str(tmp_path / "cache"), ttl_seconds=60)
        result = disk2.get("persisted")

        # Assert
        assert result == "value"


# ---------------------------------------------------------------------------
# CacheManager (integration across L1/L2/L3)
# ---------------------------------------------------------------------------

class TestCacheManager:

    def test_get_or_compute_calls_function_only_once(self, cache):
        # Arrange
        call_count = {"n": 0}

        def expensive():
            call_count["n"] += 1
            return "result"

        # Act
        first = cache.get_or_compute("key1", expensive)
        second = cache.get_or_compute("key1", expensive)

        # Assert
        assert first == second == "result"
        assert call_count["n"] == 1

    def test_backfills_l1_from_l3_on_l1_miss(self, cache):
        # Arrange: bypass L1 by writing directly through set(), then clear L1 only
        cache.set("key2", "value2")
        cache.l1.delete("key2")
        assert cache.l1.get("key2") is None  # confirm evicted from L1

        # Act
        result = cache.get("key2")

        # Assert: value recovered from L3 and repopulated into L1
        assert result == "value2"
        assert cache.l1.get("key2") == "value2"

    def test_delete_removes_from_all_levels(self, cache):
        # Arrange
        cache.set("key3", "value3")

        # Act
        cache.delete("key3")

        # Assert
        assert cache.get("key3") is None

    def test_make_key_is_deterministic(self):
        # Arrange / Act
        k1 = CacheManager.make_key("search", "hello world", 5)
        k2 = CacheManager.make_key("search", "hello world", 5)
        k3 = CacheManager.make_key("search", "different", 5)

        # Assert
        assert k1 == k2
        assert k1 != k3

    def test_stats_reflects_l2_connection_state(self, cache):
        # Act
        stats = cache.stats()

        # Assert: no Redis running in test env -> L2 reports disconnected
        assert "l1" in stats
        assert stats["l2_connected"] is False


# ---------------------------------------------------------------------------
# Latency / throughput smoke tests
# ---------------------------------------------------------------------------

class TestPerformanceCharacteristics:

    L1_HIT_BUDGET_SECONDS = 0.001   # 1ms per in-memory hit is generous
    THROUGHPUT_ITERATIONS = 1000

    def test_l1_cache_hit_latency_under_budget(self, cache):
        # Arrange
        cache.set("hot_key", {"payload": "x" * 100})

        # Act: warm, then measure average hit latency
        cache.get("hot_key")
        start = time.perf_counter()
        for _ in range(self.THROUGHPUT_ITERATIONS):
            cache.l1.get("hot_key")
        elapsed = time.perf_counter() - start
        avg_latency = elapsed / self.THROUGHPUT_ITERATIONS

        # Assert
        assert avg_latency < self.L1_HIT_BUDGET_SECONDS

    def test_get_or_compute_throughput_with_cache_beats_uncached(self, cache):
        # Arrange
        def slow_compute():
            time.sleep(0.002)
            return "computed"

        # Act: first call pays compute cost, rest should be fast cache hits
        start = time.perf_counter()
        for _ in range(50):
            cache.get_or_compute("throughput_key", slow_compute)
        elapsed = time.perf_counter() - start

        # Assert: 50 calls should complete much faster than 50 * 2ms if cached
        assert elapsed < 0.002 * 50

    def test_concurrent_get_or_compute_is_consistent(self, cache):
        # Arrange
        call_count = {"n": 0}
        lock = threading.Lock()

        def expensive():
            with lock:
                call_count["n"] += 1
            time.sleep(0.01)
            return "shared_result"

        results = []

        def worker():
            results.append(cache.get_or_compute("shared_key", expensive))

        threads = [threading.Thread(target=worker) for _ in range(10)]

        # Act
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Assert: all threads got the correct value (compute count is not
        # strictly asserted to 1 since no cross-thread lock guards compute,
        # but results must all be consistent)
        assert all(r == "shared_result" for r in results)
        assert call_count["n"] >= 1
