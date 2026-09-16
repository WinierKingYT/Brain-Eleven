"""Small local operational stores, separate from canonical memory and state."""
import hashlib
import json
import os
import time
import threading
from contextlib import contextmanager
from pathlib import Path
import tempfile
from datetime import datetime, timezone

from brain_eleven.infrastructure.locking import (
    MemoryStoreLockTimeout,
    file_lock as _base_file_lock,
)
from .path_safety import (
    RuntimePathError,
    assert_runtime_snapshot,
    ensure_runtime_directory,
    guard_runtime_path,
    runtime_root_for_path,
    validate_vault_path,
    _existing_root_check,
)


_runtime_thread_locks = {}
_runtime_thread_locks_guard = threading.Lock()


def _runtime_lock_key(target):
    """Normalize lexical aliases before deriving an OS lock identity."""
    return os.path.normcase(os.path.normpath(os.fspath(Path(target).absolute())))


@contextmanager
def _runtime_posix_lock(root, target, snapshot, timeout, poll_interval):
    import fcntl

    # Open the validated runtime directory once, then create/open a
    # target-specific marker relative to that descriptor. A parent swap after
    # this point cannot redirect the marker into an outside directory, and
    # separate marker files keep POSIX flock ownership independent per target.
    root_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    root_descriptor = os.open(root, root_flags)
    root_identity = os.fstat(root_descriptor)
    if (root_identity.st_dev, root_identity.st_ino, root_identity.st_mode, getattr(root_identity, "st_file_attributes", 0)) != snapshot.root:
        os.close(root_descriptor)
        raise RuntimePathError("Runtime root changed before lock registry open")
    try:
        lock_name = ".runtime-lock-" + hashlib.sha256(_runtime_lock_key(target).encode()).hexdigest()
        registry_descriptor = os.open(
            lock_name,
            os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0),
            0o600,
            dir_fd=root_descriptor,
        )
    except Exception:
        os.close(root_descriptor)
        raise
    acquired = False
    deadline = time.monotonic() + timeout
    key = _runtime_lock_key(target)
    with _runtime_thread_locks_guard:
        thread_lock = _runtime_thread_locks.setdefault(key, threading.Lock())
    try:
        remaining = max(0.0, deadline - time.monotonic())
        if not thread_lock.acquire(timeout=remaining):
            raise MemoryStoreLockTimeout(f"Timed out acquiring runtime lock {target}")
        try:
            while not acquired:
                try:
                    fcntl.flock(registry_descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    acquired = True
                except (BlockingIOError, OSError):
                    if time.monotonic() >= deadline:
                        raise MemoryStoreLockTimeout(f"Timed out acquiring runtime lock {target}")
                    time.sleep(poll_interval)
            yield
        finally:
            if acquired:
                fcntl.flock(registry_descriptor, fcntl.LOCK_UN)
            thread_lock.release()
    finally:
        os.close(registry_descriptor)
        os.close(root_descriptor)


@contextmanager
def _runtime_windows_mutex(target, timeout):
    import ctypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p]
    kernel32.CreateMutexW.restype = ctypes.c_void_p
    kernel32.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
    kernel32.WaitForSingleObject.restype = ctypes.c_uint32
    kernel32.ReleaseMutex.argtypes = [ctypes.c_void_p]
    kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
    name = "Local\\BrainElevenRuntime-" + hashlib.sha256(_runtime_lock_key(target).encode()).hexdigest()
    handle = kernel32.CreateMutexW(None, False, name)
    if not handle:
        raise OSError(ctypes.get_last_error(), "CreateMutexW failed")
    acquired = False
    try:
        result = kernel32.WaitForSingleObject(handle, int(max(0.0, timeout) * 1000))
        if result == 0x102:  # WAIT_TIMEOUT
            raise MemoryStoreLockTimeout(f"Timed out acquiring runtime lock {target}")
        if result not in (0, 0x80):  # WAIT_OBJECT_0 / WAIT_ABANDONED
            raise OSError(ctypes.get_last_error(), "WaitForSingleObject failed")
        acquired = True
        yield
    finally:
        if acquired:
            kernel32.ReleaseMutex(handle)
        kernel32.CloseHandle(handle)


@contextmanager
def runtime_file_lock(target, timeout=10.0, poll_interval=0.05):
    """Acquire a runtime lock without creating a raceable sidecar file."""
    target = Path(target).absolute()
    runtime_root = runtime_root_for_path(target)
    if runtime_root is None:
        with _base_file_lock(target, timeout=timeout, poll_interval=poll_interval):
            yield
        return

    snapshot = guard_runtime_path(runtime_root, target)
    # Validate once more immediately before entering the OS lock primitive.
    # POSIX creates its marker relative to an already-open runtime-root
    # descriptor; Windows uses a named mutex, so neither primitive can create
    # a marker through a swapped lexical parent.
    assert_runtime_snapshot(runtime_root, target, snapshot)
    if os.name == "nt":
        with _runtime_windows_mutex(target, timeout):
            assert_runtime_snapshot(runtime_root, target, snapshot)
            yield
    else:
        with _runtime_posix_lock(runtime_root, target, snapshot, timeout, poll_interval):
            assert_runtime_snapshot(runtime_root, target, snapshot)
            yield


# Keep the historical storage module patch point used by W-15 tests while
# routing runtime locks through the guarded wrapper.
file_lock = runtime_file_lock


def now():
    return datetime.now(timezone.utc).isoformat()


def identity(prefix, *values):
    return prefix + hashlib.sha256(json.dumps(values, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def write_json(path, value):
    path = Path(path)
    runtime_root = runtime_root_for_path(path)
    snapshot = guard_runtime_path(runtime_root, path) if runtime_root else None
    if runtime_root is None:
        path.parent.mkdir(parents=True, exist_ok=True)
    # For runtime-owned paths guard_runtime_path has created only validated
    # components.  Do not repeat mkdir: a second lookup would reopen a TOCTOU
    # window before the temp file is created.
    fd, name = tempfile.mkstemp(prefix='.' + path.name, dir=path.parent)
    try:
        if runtime_root:
            # Verify the directory identity before writing any JSON bytes.  If
            # the parent was swapped after the first guard, the temp file is
            # removed by finally without ever receiving sensitive content.
            assert_runtime_snapshot(runtime_root, path, snapshot)
        stream_fd = fd
        fd = None
        with os.fdopen(stream_fd, 'w', encoding='utf-8') as stream:
            json.dump(value, stream, ensure_ascii=False, sort_keys=True)
            stream.flush()
            os.fsync(stream.fileno())
        if runtime_root:
            # Detect a parent replacement after temp creation and immediately
            # before publication.  The lock/atomic writer semantics remain
            # unchanged for ordinary paths.
            assert_runtime_snapshot(runtime_root, path, snapshot)
        os.replace(name, path)
    finally:
        if fd is not None:
            os.close(fd)
        if os.path.exists(name):
            os.unlink(name)


def read_json(path, default=None):
    path = Path(path)
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding='utf-8'))


class RuntimeConfigConflict(ValueError):
    """Raised when a runtime-config mutation uses a stale snapshot."""


def _config_fingerprint(value):
    """Return a stable fingerprint for a validated runtime-config snapshot."""
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(payload.encode('utf-8')).hexdigest()


class RuntimeConfig:
    def __init__(self, vault):
        # Keep the validated lexical path.  Resolving after validation would
        # reopen a race in which the selected vault is swapped to a link
        # before resolve() follows it; later runtime guards must see that
        # replacement and fail closed.
        self.vault = validate_vault_path(vault)
        self.root = self.vault / '.brain-eleven' / 'runtime'
        self.path = self.root / 'config.json'

    def load(self):
        _existing_root_check(self.root)
        if os.path.lexists(self.path):
            guard_runtime_path(self.root, self.path, create=False)
        value = read_json(self.path, {'schema_version': 1, 'mode': 'OFF', 'project_ids': [], 'local_model': None,
                                      'b1_human_approval': False})
        if not isinstance(value, dict) or value.get('schema_version') != 1 or value.get('mode') not in {'OFF', 'SHADOW', 'CANARY', 'ACTIVE'}:
            raise ValueError('Invalid runtime configuration')
        # The key was introduced additively so existing vaults keep the
        # pre-B1 behavior until an operator explicitly enables it.
        value.setdefault('b1_human_approval', False)
        retrieval_mode = value.get('retrieval_mode', 'V1_LEGACY')
        # This is an additive rollout gate.  Invalid values fail closed and
        # are represented by bounded telemetry only.
        valid_retrieval = isinstance(retrieval_mode, str) and retrieval_mode in {'V1_LEGACY', 'W06B_TASK_AWARE'}
        value['retrieval_mode'] = retrieval_mode if valid_retrieval else 'V1_LEGACY'
        value['retrieval_mode_telemetry'] = None if valid_retrieval else 'RETRIEVAL_MODE_INVALID'
        if not isinstance(value['b1_human_approval'], bool):
            raise ValueError('Invalid B1 human approval configuration')
        if not isinstance(value.get('project_ids'), list) or not all(isinstance(x, str) and x for x in value['project_ids']):
            raise ValueError('Invalid runtime project scope')
        model = value.get('local_model')
        if model is not None and (not isinstance(model, dict) or set(model) != {'url', 'model'} or not all(isinstance(x, str) and x for x in model.values())):
            raise ValueError('Invalid local model configuration')
        return value

    def ensure_root(self):
        """Create the vault-owned runtime root after no-follow validation."""
        return ensure_runtime_directory(self.root, self.root)

    def set_mode(self, mode):
        if mode not in {'OFF', 'SHADOW', 'CANARY', 'ACTIVE'}:
            raise ValueError('Invalid rollout mode')
        value = self.load()
        snapshot = _config_fingerprint(value)
        if mode == 'CANARY':
            from brain_eleven.memory import MemoryStore
            from brain_eleven.state import StateStore
            if MemoryStore(self.vault).load()['schema_version'] != 3 or StateStore(self.vault).load()['schema_version'] != 2 or not value['project_ids']:
                raise ValueError('Install and migrate the opted-in canary project first')
            from evals.runtime_eval import run
            report = run('holdout')
            write_json(self.root / 'canary-quality.json', report)
            if report['status'] != 'PASS':
                raise ValueError('Independent holdout quality gates failed; remain in SHADOW')
        if mode == 'ACTIVE':
            from .graduation import verify
            verify(self.vault)

        def mutate(current):
            current['mode'] = mode

        return self._commit(snapshot, mutate)

    def set_human_approval(self, enabled):
        """Enable or disable B1's human approval boundary explicitly."""
        if not isinstance(enabled, bool):
            raise ValueError('Human approval flag must be boolean')
        value = self.load()
        snapshot = _config_fingerprint(value)

        def mutate(current):
            current['b1_human_approval'] = enabled

        return self._commit(snapshot, mutate)

    def _commit(self, expected_fingerprint, mutate):
        """Apply one config mutation only if its validated snapshot is current."""
        with file_lock(self.path):
            current = self.load()
            actual_fingerprint = _config_fingerprint(current)
            if actual_fingerprint != expected_fingerprint:
                raise RuntimeConfigConflict('Runtime configuration changed; retry')
            mutate(current)
            write_json(self.path, current)
            return current

    def _mutate_current(self, mutate):
        """Atomically mutate the latest config for internal runtime callers."""
        with file_lock(self.path):
            current = self.load()
            mutate(current)
            write_json(self.path, current)
            return current
