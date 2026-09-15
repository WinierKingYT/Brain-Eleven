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
    *,
    before_open=None,
    create_parent: bool = True,
    cleanup_on_error=None,
) -> Iterator[None]:
    """Lock a persistent sidecar file until the mutation is complete."""
    target = Path(target_path)
    lock_path = target.with_name(f"{target.name}.lock")
    if before_open is not None:
        before_open()
    if create_parent:
        lock_path.parent.mkdir(parents=True, exist_ok=True)
    created = False
    handle = None
    acquired = False
    entered = False
    cleanup_required = False
    try:
        # Try exclusive creation first.  This lets failure cleanup distinguish
        # a marker created by this call from an already-existing contender.
        try:
            descriptor = os.open(
                lock_path,
                os.O_CREAT | os.O_EXCL | os.O_RDWR,
                0o666,
            )
            created = True
            handle = os.fdopen(descriptor, "a+", encoding="utf-8")
        except FileExistsError:
            if os.name == "nt":
                # Preserve the historical sharing mode used by msvcrt for a
                # contender that opens an existing marker on Windows.
                handle = open(lock_path, "a+", encoding="utf-8")
            else:
                descriptor = os.open(lock_path, os.O_RDWR)
                handle = os.fdopen(descriptor, "a+", encoding="utf-8")
    except Exception:
        if created and cleanup_on_error is not None:
            cleanup_on_error(lock_path)
        raise
    deadline = time.monotonic() + timeout
    try:
        if before_open is not None:
            before_open()
        while not acquired:
            if before_open is not None:
                before_open()
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

            if acquired and before_open is not None:
                before_open()

        entered = True
        yield
    except Exception:
        cleanup_required = not entered and created and cleanup_on_error is not None
        raise
    finally:
        if acquired and handle is not None:
            if os.name == "nt":
                import msvcrt

                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        if handle is not None:
            handle.close()
        if cleanup_required:
            cleanup_on_error(lock_path)


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
