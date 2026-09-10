"""Stable support-package boundary for support utilities.

Logging now has its canonical implementation in this package.  The remaining
support utilities continue to use the cached legacy loader during the
compatibility window.
"""

from __future__ import annotations

from brain_eleven._legacy import load_legacy_module
from brain_eleven.support.logging import (
    ColoredFormatter,
    JSONFormatter,
    logger,
    setup_logging,
)


_summarizer = load_legacy_module("summarizer", "summarizer.py")
_anomaly_detector = load_legacy_module("anomaly_detector", "anomaly_detector.py")
_cache_manager = load_legacy_module("cache_manager", "cache_manager.py")

MemorySummarizer = _summarizer.MemorySummarizer
tokenize = _summarizer.tokenize
jaccard_similarity = _summarizer.jaccard_similarity

AnomalyDetector = _anomaly_detector.AnomalyDetector

LRUCache = _cache_manager.LRUCache
DiskCache = _cache_manager.DiskCache
CacheManager = _cache_manager.CacheManager
REDIS_AVAILABLE = _cache_manager.REDIS_AVAILABLE

__all__ = [
    "AnomalyDetector",
    "CacheManager",
    "ColoredFormatter",
    "DiskCache",
    "JSONFormatter",
    "LRUCache",
    "MemorySummarizer",
    "REDIS_AVAILABLE",
    "jaccard_similarity",
    "logger",
    "setup_logging",
    "tokenize",
]
