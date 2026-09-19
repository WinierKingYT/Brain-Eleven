"""Stable package surface for the durable native capture queue.

The script remains the copied-hook entrypoint, while runtime consumers use
this identity-preserving package surface.  The shared loader prevents the
package and legacy paths from creating separate queue classes or error types.
"""

from __future__ import annotations

from brain_eleven._legacy import load_legacy_module


_legacy = load_legacy_module("capture_queue", "capture_queue.py")

CAPTURE_QUEUE_SCHEMA_VERSION = _legacy.CAPTURE_QUEUE_SCHEMA_VERSION
JOB_PREFIX = _legacy.JOB_PREFIX
QUEUED = _legacy.QUEUED
CLAIMED = _legacy.CLAIMED
PROCESSING = _legacy.PROCESSING
COMMITTED = _legacy.COMMITTED
DEAD_LETTER = _legacy.DEAD_LETTER
JOB_STATUSES = _legacy.JOB_STATUSES
QUEUE_DIRECTORIES = _legacy.QUEUE_DIRECTORIES
CaptureQueueError = _legacy.CaptureQueueError
CaptureQueueFullError = _legacy.CaptureQueueFullError
CaptureQueueCorruptError = _legacy.CaptureQueueCorruptError
CaptureQueueStateError = _legacy.CaptureQueueStateError
CaptureQueueWriteError = _legacy.CaptureQueueWriteError
CaptureQueueLockError = _legacy.CaptureQueueLockError
CaptureQueueConfig = _legacy.CaptureQueueConfig
QueueReceipt = _legacy.QueueReceipt
CaptureQueue = _legacy.CaptureQueue
main = _legacy.main

__all__ = [
    "CAPTURE_QUEUE_SCHEMA_VERSION",
    "JOB_PREFIX",
    "QUEUED",
    "CLAIMED",
    "PROCESSING",
    "COMMITTED",
    "DEAD_LETTER",
    "JOB_STATUSES",
    "QUEUE_DIRECTORIES",
    "CaptureQueueError",
    "CaptureQueueFullError",
    "CaptureQueueCorruptError",
    "CaptureQueueStateError",
    "CaptureQueueWriteError",
    "CaptureQueueLockError",
    "CaptureQueueConfig",
    "QueueReceipt",
    "CaptureQueue",
    "main",
]
