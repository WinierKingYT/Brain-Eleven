"""Stable support-package boundary for support utilities.

Logging, cache, summarizer and anomaly detection all have their canonical
implementation in this package.
"""

from __future__ import annotations

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
from brain_eleven.support.summarizer import (
    MemorySummarizer,
    jaccard_similarity,
    tokenize,
)
from brain_eleven.support.anomaly import AnomalyDetector

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
