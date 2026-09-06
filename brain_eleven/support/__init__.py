"""Stable support-package boundary for legacy utility implementations.

PRE-12 keeps the existing logging, digest, anomaly, and cache behavior
unchanged while giving callers one import surface.  The legacy scripts remain
the backing implementations during the compatibility window.
"""

from __future__ import annotations

from brain_eleven._legacy import load_legacy_module


_logging = load_legacy_module("logging_config", "logging_config.py")
_summarizer = load_legacy_module("summarizer", "summarizer.py")
_anomaly_detector = load_legacy_module("anomaly_detector", "anomaly_detector.py")
_cache_manager = load_legacy_module("cache_manager", "cache_manager.py")

JSONFormatter = _logging.JSONFormatter
ColoredFormatter = _logging.ColoredFormatter
setup_logging = _logging.setup_logging

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
    "setup_logging",
    "tokenize",
]
