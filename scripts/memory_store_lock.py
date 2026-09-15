#!/usr/bin/env python3
"""Small cross-platform lock for canonical memory-store mutations."""

import os
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Union


class MemoryStoreLockTimeout(TimeoutError):
    """Raised when the canonical store lock cannot be acquired in time."""


@contextmanager
def file_lock(
    target_path: Union[str, Path],
    timeout: float = 10.0,
    poll_interval: float = 0.05,
) -> Iterator[None]:
    """Lock a persistent sidecar file until the mutation is complete."""
    target = Path(target_path)
    lock_path = target.with_name(f"{target.name}.lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    handle = open(lock_path, "a+", encoding="utf-8")
    acquired = False
    deadline = time.monotonic() + timeout
    try:
        while not acquired:
            try:
                if os.name == "nt":
                    import msvcrt

                    handle.seek(0)
                    handle.write(" ")
                    handle.flush()
                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                acquired = True
            except (BlockingIOError, OSError):
                if time.monotonic() >= deadline:
                    raise MemoryStoreLockTimeout(f"Timed out acquiring {lock_path}")
                time.sleep(poll_interval)

        yield
    finally:
        if acquired:
            if os.name == "nt":
                import msvcrt

                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        handle.close()


@contextmanager
def memory_store_lock(
    vault_path: Union[str, Path],
    timeout: float = 10.0,
    poll_interval: float = 0.05,
) -> Iterator[None]:
    """Lock the canonical memory store until the mutation is complete."""
    target = Path(vault_path) / ".claude" / "validated-memory.json"
    with file_lock(target, timeout=timeout, poll_interval=poll_interval):
        yield
