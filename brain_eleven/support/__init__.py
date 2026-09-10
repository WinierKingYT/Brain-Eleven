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
from brain_eleven.support.cache import (
    CacheManager,
    DiskCache,
    LRUCache,
    REDIS_AVAILABLE,
)


_summarizer = load_legacy_module("summarizer", "summarizer.py")
_anomaly_detector = load_legacy_module("anomaly_detector", "anomaly_detector.py")
_cache_manager_adapter = load_legacy_module("cache_manager", "cache_manager.py")

MemorySummarizer = _summarizer.MemorySummarizer
tokenize = _summarizer.tokenize
jaccard_similarity = _summarizer.jaccard_similarity

AnomalyDetector = _anomaly_detector.AnomalyDetector

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
