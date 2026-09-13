#!/usr/bin/env python3
"""Create and restore verified backups of Brain-Eleven canonical memory.

The canonical store is the authority.  Knowledge graphs, context bootstraps,
compiled candidates, and caches are deliberately excluded: a restore must
prove that those projections can be rebuilt from canonical data.
"""

import argparse
import ctypes
import hashlib
import importlib.util
import json
import os
import shutil
import sys
import tempfile
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Dict, Iterable, List, Optional, Tuple, Union

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from brain_eleven.extraction import EntityExtractor
from brain_eleven.infrastructure.locking import MemoryStoreLockTimeout, file_lock
from brain_eleven.memory import (
    GLOBAL_SCOPE,
    PROJECT_SCOPE,
    infer_memory_scope,
    scoped_fingerprint,
)
from brain_eleven.memory import CANONICAL_SCHEMA_VERSION, MemoryStore, MemoryStoreCorrupt
from brain_eleven.projects.registry import (
    REGISTRY_FILENAME,
    ProjectRegistry,
    ProjectRegistryError,
)
from brain_eleven.state import StateSchemaError, StateStore, validate_state_document


BACKUP_SCHEMA_VERSION = 3
SUPPORTED_BACKUP_SCHEMA_VERSIONS = frozenset({1, 2, BACKUP_SCHEMA_VERSION})
BACKUP_FORMAT = "brain-eleven-memory-backup"
MANIFEST_PATH = "manifest.json"
CANONICAL_ARCHIVE_PATH = "canonical/validated-memory.json"
REGISTRY_ARCHIVE_PATH = "registry/project-registry.json"
SETTINGS_ARCHIVE_PATH = "config/settings.json"
STATE_ARCHIVE_PATH = "state/project-state.json"
SOURCE_ARCHIVE_PATHS = (
    CANONICAL_ARCHIVE_PATH,
    REGISTRY_ARCHIVE_PATH,
    SETTINGS_ARCHIVE_PATH,
    STATE_ARCHIVE_PATH,
)
OPTIONAL_SOURCE_PATHS = frozenset(
    {REGISTRY_ARCHIVE_PATH, SETTINGS_ARCHIVE_PATH, STATE_ARCHIVE_PATH}
)
SNAPSHOT_PROTOCOL = "stable-read-validate-retry-v1"
MAX_SNAPSHOT_ATTEMPTS = 3
SNAPSHOT_ATTEMPT_BUDGET_SECONDS = 5.0
ARCHIVE_PUBLICATION_LOCK_TIMEOUT_SECONDS = 5.0
_WINDOWS_FILE_ATTRIBUTE_REPARSE_POINT = 0x400
_WINDOWS_FILE_FLAG_OPEN_REPARSE_POINT = 0x00200000
_WINDOWS_FILE_FLAG_BACKUP_SEMANTICS = 0x02000000

RESTORE_PATHS = {
    CANONICAL_ARCHIVE_PATH: Path(".claude") / "validated-memory.json",
    REGISTRY_ARCHIVE_PATH: Path(".claude") / REGISTRY_FILENAME,
    SETTINGS_ARCHIVE_PATH: Path(".claude") / "settings.json",
    STATE_ARCHIVE_PATH: Path(".claude") / "project-state.json",
}


class MemoryBackupError(RuntimeError):
    """Raised when a backup cannot be trusted, created, or safely restored."""


class MemoryBackupConsistencyError(MemoryBackupError):
    """Raised when the bounded source snapshot cannot be made stable."""

    def __init__(self, changed_sources: Tuple[str, ...], attempts: int, reason: str):
        self.changed_sources = tuple(changed_sources)
        self.attempts = int(attempts)
        self.reason = str(reason)
        safe_sources = ",".join(self.changed_sources) if self.changed_sources else "none"
        super().__init__(
            f"Backup source consistency failure: {self.reason}; "
            f"attempts={self.attempts}; sources={safe_sources}"
        )


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _lexists(path: Path) -> bool:
    """Return whether a path exists, including a broken symbolic link."""
    return os.path.lexists(str(path))


def _is_reparse_or_symlink(path: Path) -> bool:
    """Reject links and Windows reparse points before opening a source."""
    try:
        stat_result = path.lstat()
    except OSError as exc:
        raise MemoryBackupError("Cannot inspect backup source path") from exc
    if path.is_symlink():
        return True
    attributes = getattr(stat_result, "st_file_attributes", 0)
    return bool(attributes & _WINDOWS_FILE_ATTRIBUTE_REPARSE_POINT)


def _absolute_vault(vault_path: Union[str, Path]) -> Path:
    candidate = Path(vault_path).expanduser()
    if not candidate.is_absolute():
        candidate = Path.cwd() / candidate
    return candidate


def _assert_source_root(vault: Path) -> Path:
    """Validate the vault and .claude directory without following links."""
    if not _lexists(vault) or not vault.is_dir():
        raise MemoryBackupError("Backup vault does not exist")
    if _is_reparse_or_symlink(vault):
        raise MemoryBackupError("Backup vault must not be a symbolic link or reparse point")
    claude = vault / ".claude"
    if not _lexists(claude) or not claude.is_dir():
        raise MemoryBackupError("Backup vault is missing its .claude directory")
    if _is_reparse_or_symlink(claude):
        raise MemoryBackupError("Backup .claude directory must not be a symbolic link or reparse point")
    return claude


def _read_windows_no_follow(path: Path, containment_root: Path) -> bytes:
    """Read a regular file through a reparse-point-aware Windows handle."""
    import msvcrt

    try:
        if os.path.commonpath((os.path.abspath(str(containment_root)), os.path.abspath(str(path)))) != os.path.abspath(str(containment_root)):
            raise MemoryBackupError("Backup source escapes the selected .claude directory")
    except ValueError as exc:
        raise MemoryBackupError("Backup source escapes the selected .claude directory") from exc

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    create_file = kernel32.CreateFileW
    create_file.argtypes = [
        ctypes.c_wchar_p,
        ctypes.c_uint32,
        ctypes.c_uint32,
        ctypes.c_void_p,
        ctypes.c_uint32,
        ctypes.c_uint32,
        ctypes.c_void_p,
    ]
    create_file.restype = ctypes.c_void_p
    invalid = ctypes.c_void_p(-1).value
    handle = create_file(
        str(path),
        0x80000000,  # GENERIC_READ
        0x00000001 | 0x00000002 | 0x00000004,  # share read/write/delete
        None,
        3,  # OPEN_EXISTING
        _WINDOWS_FILE_FLAG_OPEN_REPARSE_POINT | _WINDOWS_FILE_FLAG_BACKUP_SEMANTICS,
        None,
    )
    if handle in (None, invalid):
        raise OSError(ctypes.get_last_error(), "Cannot open backup source")
    raw_handle = handle
    descriptor = None
    try:
        descriptor = msvcrt.open_osfhandle(int(handle), os.O_RDONLY | getattr(os, "O_BINARY", 0))
        handle = None
        before = os.fstat(descriptor)
        chunks = []
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        after = os.fstat(descriptor)
        if (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino):
            raise MemoryBackupError("Backup source identity changed while reading")
        get_final_path = kernel32.GetFinalPathNameByHandleW
        get_final_path.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_uint32, ctypes.c_uint32]
        get_final_path.restype = ctypes.c_uint32
        final_buffer = ctypes.create_unicode_buffer(32768)
        final_length = get_final_path(raw_handle, final_buffer, len(final_buffer), 0)
        if not final_length or final_length >= len(final_buffer):
            raise MemoryBackupError("Cannot verify backup source containment")
        final_path = final_buffer.value
        if final_path.startswith("\\\\?\\"):
            final_path = final_path[4:]
        try:
            if os.path.commonpath((os.path.abspath(str(containment_root)), os.path.abspath(final_path))) != os.path.abspath(str(containment_root)):
                raise MemoryBackupError("Backup source escapes the selected .claude directory")
        except ValueError as exc:
            raise MemoryBackupError("Backup source escapes the selected .claude directory") from exc
        # FILE_FLAG_OPEN_REPARSE_POINT prevents following the final reparse
        # point.  The lstat check below remains a defence against a path swap
        # between the pre-open check and handle creation.
        if _is_reparse_or_symlink(path):
            raise MemoryBackupError("Backup source must not be a symbolic link or reparse point")
        return b"".join(chunks)
    finally:
        if descriptor is not None:
            os.close(descriptor)
        elif handle not in (None, invalid):
            kernel32.CloseHandle(handle)


def _read_source_file(path: Path, containment_root: Path) -> bytes:
    """Read one source with no-follow and identity checks."""
    if not _lexists(path):
        raise FileNotFoundError(path)
    if _is_reparse_or_symlink(path):
        raise MemoryBackupError("Backup source must not be a symbolic link or reparse point")
    if not path.is_file():
        raise MemoryBackupError("Backup source must be a regular file")
    before_path = path.lstat()
    if os.name == "nt":
        payload = _read_windows_no_follow(path, containment_root)
    else:
        flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
        if not getattr(os, "O_NOFOLLOW", 0):
            raise MemoryBackupError("Backup source no-follow support is unavailable")
        descriptor = None
        try:
            descriptor = os.open(str(path), flags)
            before = os.fstat(descriptor)
            chunks = []
            while True:
                chunk = os.read(descriptor, 1024 * 1024)
                if not chunk:
                    break
                chunks.append(chunk)
            after = os.fstat(descriptor)
            if (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino):
                raise MemoryBackupError("Backup source identity changed while reading")
            payload = b"".join(chunks)
        except FileNotFoundError:
            raise
        except OSError as exc:
            raise MemoryBackupError("Cannot read backup source") from exc
        finally:
            if descriptor is not None:
                os.close(descriptor)
    try:
        after_path = path.lstat()
    except OSError as exc:
        raise MemoryBackupError("Backup source identity changed while reading") from exc
    if (before_path.st_dev, before_path.st_ino) != (after_path.st_dev, after_path.st_ino):
        raise MemoryBackupError("Backup source identity changed while reading")
    return payload


def _json_object(payload: bytes, label: str) -> Dict:
    def _pairs_without_duplicates(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate JSON key")
            result[key] = value
        return result

    try:
        value = json.loads(payload.decode("utf-8"), object_pairs_hook=_pairs_without_duplicates)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise MemoryBackupError(f"{label} is not valid UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise MemoryBackupError(f"{label} must be a JSON object")
    return value


def _validate_memory_record(record: Dict, bucket: str, index: int) -> Tuple[str, str]:
    if not isinstance(record, dict):
        raise MemoryBackupError(f"{bucket}[{index}] must be a memory object")

    memory_id = record.get("memory_id")
    if not isinstance(memory_id, str) or not memory_id.strip():
        raise MemoryBackupError(f"{bucket}[{index}] has no stable memory_id")

    content = record.get("content")
    memory_type = record.get("type")
    if not isinstance(content, str) or not content.strip():
        raise MemoryBackupError(f"{bucket}[{index}] has no memory content")
    if not isinstance(memory_type, str) or not memory_type.strip():
        raise MemoryBackupError(f"{bucket}[{index}] has no memory type")

    raw_scope = record.get("scope")
    if raw_scope not in {GLOBAL_SCOPE, PROJECT_SCOPE}:
        raise MemoryBackupError(f"{bucket}[{index}] has unsupported memory scope")
    scope, _project, project_id = infer_memory_scope(record)
    if scope == PROJECT_SCOPE and not project_id:
        raise MemoryBackupError(f"{bucket}[{index}] project memory has no project_id")
    if scope == GLOBAL_SCOPE and (
        str(record.get("project") or "").strip()
        or str(record.get("project_id") or "").strip()
    ):
        raise MemoryBackupError(f"{bucket}[{index}] global memory carries project metadata")

    fingerprint = record.get("dedup_fingerprint")
    expected_fingerprint = scoped_fingerprint(content, scope, project_id, memory_type)
    if fingerprint != expected_fingerprint:
        raise MemoryBackupError(
            f"{bucket}[{index}] has an invalid scope-aware dedup fingerprint"
        )
    return memory_id, project_id if scope == PROJECT_SCOPE else ""


def _validate_canonical_document(payload: bytes) -> Tuple[Dict, List[str], List[str]]:
    """Validate the raw canonical document without normalizing or rewriting it."""
    document = _json_object(payload, "canonical memory")
    if document.get("schema_version") not in {CANONICAL_SCHEMA_VERSION, 3}:
        raise MemoryBackupError(
            "Canonical memory must use the current schema before backup; "
            "run the scoped-memory migration first"
        )
    try:
        normalized = MemoryStore._normalize(document)
    except MemoryStoreCorrupt as exc:
        raise MemoryBackupError(f"Canonical memory is invalid: {exc}") from exc

    seen_ids = set()
    project_ids = set()
    for bucket in ("validated_memory", "rejected_memory"):
        records = normalized[bucket]
        for index, record in enumerate(records):
            memory_id, project_id = _validate_memory_record(record, bucket, index)
            if memory_id in seen_ids:
                raise MemoryBackupError("Canonical memory has duplicate memory_id")
            seen_ids.add(memory_id)
            if project_id:
                project_ids.add(project_id)
    return normalized, sorted(seen_ids), sorted(project_ids)


def _validate_registry_payload(payload: bytes) -> Dict:
    document = _json_object(payload, "project registry")
    # Reuse the canonical registry validator without writing a second copy.
    ProjectRegistry._validate(document)
    return document


def _validate_state_payload(payload: bytes) -> Dict:
    document = _json_object(payload, "project state")
    try:
        return validate_state_document(document)
    except StateSchemaError as exc:
        raise MemoryBackupError("Project state is invalid") from exc


def _validate_snapshot(payloads: Dict[str, bytes]) -> Dict:
    if CANONICAL_ARCHIVE_PATH not in payloads:
        raise MemoryBackupError("Backup is missing canonical memory")

    canonical, memory_ids, project_ids = _validate_canonical_document(
        payloads[CANONICAL_ARCHIVE_PATH]
    )
    registry = None
    if REGISTRY_ARCHIVE_PATH in payloads:
        registry = _validate_registry_payload(payloads[REGISTRY_ARCHIVE_PATH])
    if SETTINGS_ARCHIVE_PATH in payloads:
        _json_object(payloads[SETTINGS_ARCHIVE_PATH], "settings")
    project_state = None
    if STATE_ARCHIVE_PATH in payloads:
        project_state = _validate_state_payload(payloads[STATE_ARCHIVE_PATH])

    if project_ids:
        if registry is None:
            raise MemoryBackupError("Project-scoped memory requires a project registry backup")
        registered_ids = {project["project_id"] for project in registry["projects"]}
        missing = sorted(set(project_ids) - registered_ids)
        if missing:
            raise MemoryBackupError("Project registry is missing canonical project identities")

    if project_state is not None:
        if registry is None:
            raise MemoryBackupError("Canonical project state requires a project registry backup")
        registered_ids = {project["project_id"] for project in registry["projects"]}
        state_project_ids = set(project_state["projects"])
        missing_state_projects = sorted(state_project_ids - registered_ids)
        if missing_state_projects:
            raise MemoryBackupError("Project registry is missing canonical state identities")

    return {
        "canonical": canonical,
        "memory_ids": memory_ids,
        "project_ids": project_ids,
        "registry": registry,
        "state": project_state,
    }


def _source_descriptors(payloads: Dict[str, bytes]) -> Dict[str, Dict]:
    """Build privacy-safe descriptors for the fixed source set."""
    unknown = set(payloads) - set(SOURCE_ARCHIVE_PATHS)
    if unknown:
        raise MemoryBackupError("Backup source set contains an unknown path")

    descriptors = {}
    canonical_payload = payloads.get(CANONICAL_ARCHIVE_PATH)
    if canonical_payload is None:
        raise MemoryBackupError("Backup is missing canonical memory")
    canonical_raw = _json_object(canonical_payload, "canonical memory")
    canonical_normalized = MemoryStore._normalize(canonical_raw)
    descriptors[CANONICAL_ARCHIVE_PATH] = {
        "present": True,
        "sha256": _sha256(canonical_payload),
        "bytes": len(canonical_payload),
        "raw_schema_version": canonical_raw.get("schema_version"),
        "normalized_schema_version": canonical_normalized.get("schema_version"),
        "revision": canonical_normalized.get("revision"),
    }

    registry_payload = payloads.get(REGISTRY_ARCHIVE_PATH)
    if registry_payload is None:
        descriptors[REGISTRY_ARCHIVE_PATH] = {
            "present": False,
            "sha256": None,
            "bytes": 0,
            "raw_schema_version": None,
            "normalized_schema_version": None,
            "revision": None,
            "revision_origin": None,
        }
    else:
        registry_raw = _json_object(registry_payload, "project registry")
        registry_normalized = ProjectRegistry._normalize(registry_raw)
        descriptors[REGISTRY_ARCHIVE_PATH] = {
            "present": True,
            "sha256": _sha256(registry_payload),
            "bytes": len(registry_payload),
            "raw_schema_version": registry_raw.get("schema_version"),
            "normalized_schema_version": registry_normalized.get("schema_version"),
            "revision": registry_normalized.get("revision"),
            "revision_origin": "document" if "revision" in registry_raw else "legacy_default",
        }

    settings_payload = payloads.get(SETTINGS_ARCHIVE_PATH)
    descriptors[SETTINGS_ARCHIVE_PATH] = (
        {
            "present": False,
            "sha256": None,
            "bytes": 0,
            "revision": None,
        }
        if settings_payload is None
        else {
            "present": True,
            "sha256": _sha256(settings_payload),
            "bytes": len(settings_payload),
            "revision": None,
        }
    )

    state_payload = payloads.get(STATE_ARCHIVE_PATH)
    if state_payload is None:
        descriptors[STATE_ARCHIVE_PATH] = {
            "present": False,
            "sha256": None,
            "bytes": 0,
            "schema_version": None,
            "store_revision": None,
        }
    else:
        state_raw = _json_object(state_payload, "project state")
        state_normalized = _validate_state_payload(state_payload)
        descriptors[STATE_ARCHIVE_PATH] = {
            "present": True,
            "sha256": _sha256(state_payload),
            "bytes": len(state_payload),
            "schema_version": state_raw.get("schema_version"),
            "store_revision": state_normalized.get("store_revision"),
        }
    return {path: descriptors[path] for path in SOURCE_ARCHIVE_PATHS}


def _source_snapshot_digest(descriptors: Dict[str, Dict]) -> str:
    ordered = {path: descriptors[path] for path in SOURCE_ARCHIVE_PATHS}
    encoded = json.dumps(
        ordered,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return _sha256(encoded)


def _read_source_payloads(vault_path: Union[str, Path]) -> Dict[str, bytes]:
    vault = _absolute_vault(vault_path)
    claude = _assert_source_root(vault)
    paths = {
        archive_path: vault / RESTORE_PATHS[archive_path]
        for archive_path in SOURCE_ARCHIVE_PATHS
    }
    canonical_path = paths[CANONICAL_ARCHIVE_PATH]
    if not _lexists(canonical_path):
        raise MemoryBackupError("Canonical memory does not exist")

    payloads: Dict[str, bytes] = {}
    for archive_path in SOURCE_ARCHIVE_PATHS:
        path = paths[archive_path]
        if not _lexists(path):
            if archive_path == CANONICAL_ARCHIVE_PATH:
                raise MemoryBackupError("Canonical memory does not exist")
            continue
        try:
            payloads[archive_path] = _read_source_file(path, claude)
        except FileNotFoundError:
            if archive_path == CANONICAL_ARCHIVE_PATH:
                raise MemoryBackupError("Canonical memory does not exist") from None
            # An optional source disappearing during this pass is represented
            # as absent; the second pass will detect a change if it reappears.
            continue
    _validate_snapshot(payloads)
    return payloads


def _read_source_pass(vault_path: Union[str, Path]) -> Tuple[Dict[str, bytes], Dict, Dict[str, Dict]]:
    payloads = _read_source_payloads(vault_path)
    snapshot = _validate_snapshot(payloads)
    descriptors = _source_descriptors(payloads)
    return payloads, snapshot, descriptors


def _changed_source_paths(first: Dict[str, bytes], second: Dict[str, bytes], first_descriptors: Dict, second_descriptors: Dict) -> Tuple[str, ...]:
    changed = []
    for archive_path in SOURCE_ARCHIVE_PATHS:
        if first.get(archive_path) != second.get(archive_path) or first_descriptors.get(archive_path) != second_descriptors.get(archive_path):
            changed.append(archive_path)
    return tuple(changed)


def _stable_source_snapshot(vault_path: Union[str, Path]) -> Tuple[Dict[str, bytes], Dict, Dict[str, Dict], int]:
    """Read and validate all sources twice, retrying bounded source churn."""
    last_changed: Tuple[str, ...] = tuple()
    last_reason = "source_churn"
    vault = _absolute_vault(vault_path)
    for attempt in range(1, MAX_SNAPSHOT_ATTEMPTS + 1):
        started = time.monotonic()
        first_payloads, _first_snapshot, first_descriptors = _read_source_pass(vault)
        if time.monotonic() - started > SNAPSHOT_ATTEMPT_BUDGET_SECONDS:
            raise MemoryBackupConsistencyError(last_changed, attempt, "read_budget_exceeded")
        second_payloads, second_snapshot, second_descriptors = _read_source_pass(vault)
        elapsed = time.monotonic() - started
        if elapsed > SNAPSHOT_ATTEMPT_BUDGET_SECONDS:
            raise MemoryBackupConsistencyError(last_changed, attempt, "read_budget_exceeded")
        changed = _changed_source_paths(
            first_payloads,
            second_payloads,
            first_descriptors,
            second_descriptors,
        )
        if not changed:
            return second_payloads, second_snapshot, second_descriptors, attempt
        last_changed = changed
        required_changed = CANONICAL_ARCHIVE_PATH in changed
        last_reason = "source_churn" if required_changed else "optional_source_changed"
    raise MemoryBackupConsistencyError(last_changed, MAX_SNAPSHOT_ATTEMPTS, last_reason)


def _manifest_for(
    payloads: Dict[str, bytes],
    snapshot: Dict,
    descriptors: Dict[str, Dict],
    attempts: int,
) -> Dict:
    files = [
        {
            "path": archive_path,
            "sha256": _sha256(payload),
            "bytes": len(payload),
        }
        for archive_path, payload in sorted(payloads.items())
    ]
    return {
        "schema_version": BACKUP_SCHEMA_VERSION,
        "format": BACKUP_FORMAT,
        "archive_id": f"backup_{os.urandom(12).hex()}",
        "created_at": _utc_now(),
        "canonical": {
            "schema_version": snapshot["canonical"]["schema_version"],
            "revision": int(snapshot["canonical"]["revision"]),
            "memory_count": len(snapshot["memory_ids"]),
            "project_count": len(snapshot["project_ids"]),
        },
        "state": {
            "schema_version": snapshot["state"]["schema_version"] if snapshot["state"] else None,
            "project_count": len(snapshot["state"]["projects"]) if snapshot["state"] else 0,
        },
        "migration": {
            "name": "scope-v2",
            "canonical_schema_version": snapshot["canonical"]["schema_version"],
            "scope_metadata": "embedded_in_canonical_records",
        },
        "files": files,
        "snapshot": {
            "protocol": SNAPSHOT_PROTOCOL,
            "attempts": attempts,
            "verified_at": _utc_now(),
            "source_snapshot_sha256": _source_snapshot_digest(descriptors),
            "sources": descriptors,
        },
    }


def _atomic_create_archive(output_path: Path, manifest: Dict, payloads: Dict[str, bytes]) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=".memory-backup-", suffix=".zip", dir=output_path.parent
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    published = False
    try:
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr(MANIFEST_PATH, json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
            for archive_path, payload in sorted(payloads.items()):
                archive.writestr(archive_path, payload)
        with temporary.open("r+b") as handle:
            os.fsync(handle.fileno())
        try:
            with file_lock(output_path, timeout=ARCHIVE_PUBLICATION_LOCK_TIMEOUT_SECONDS):
                if output_path.exists():
                    raise MemoryBackupError("Backup archive already exists")
                temporary.replace(output_path)
                published = True
                _fsync_parent_directory(output_path)
        except (MemoryStoreLockTimeout, TimeoutError) as exc:
            raise MemoryBackupError("archive publication lock timeout") from exc
    except MemoryBackupError:
        raise
    except (OSError, zipfile.BadZipFile) as exc:
        if published and output_path.exists():
            try:
                output_path.unlink()
            except OSError:
                pass
        raise MemoryBackupError("Cannot create backup archive") from exc
    finally:
        if temporary.exists():
            temporary.unlink()


def _fsync_parent_directory(path: Path) -> None:
    """Persist an archive directory entry where directory fsync is supported."""
    if os.name == "nt":
        return
    descriptor = os.open(str(path.parent), os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _expected_archive_path(path: str) -> bool:
    pure = PurePosixPath(path)
    return (
        path in RESTORE_PATHS
        and not pure.is_absolute()
        and ".." not in pure.parts
        and "\\" not in path
    )


def _verify_schema3_snapshot(manifest: Dict, payloads: Dict[str, bytes]) -> None:
    snapshot = manifest.get("snapshot")
    if not isinstance(snapshot, dict):
        raise MemoryBackupError("Backup manifest has no snapshot metadata")
    if snapshot.get("protocol") != SNAPSHOT_PROTOCOL:
        raise MemoryBackupError("Backup manifest has an unsupported snapshot protocol")
    attempts = snapshot.get("attempts")
    if isinstance(attempts, bool) or not isinstance(attempts, int) or not 1 <= attempts <= MAX_SNAPSHOT_ATTEMPTS:
        raise MemoryBackupError("Backup manifest has invalid snapshot attempts")
    if not isinstance(snapshot.get("verified_at"), str) or not snapshot["verified_at"]:
        raise MemoryBackupError("Backup manifest has invalid snapshot verification time")
    digest = snapshot.get("source_snapshot_sha256")
    if not isinstance(digest, str) or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
        raise MemoryBackupError("Backup manifest has invalid snapshot digest")
    sources = snapshot.get("sources")
    if not isinstance(sources, dict) or set(sources) != set(SOURCE_ARCHIVE_PATHS):
        raise MemoryBackupError("Backup manifest has an invalid source descriptor set")
    expected_descriptors = _source_descriptors(payloads)
    if sources != expected_descriptors:
        raise MemoryBackupError("Backup manifest source descriptors do not match archived bytes")
    if digest != _source_snapshot_digest(expected_descriptors):
        raise MemoryBackupError("Backup manifest source snapshot digest mismatch")
    listed_paths = {
        entry.get("path")
        for entry in manifest.get("files", [])
        if isinstance(entry, dict)
    }
    present_paths = {
        path for path, descriptor in sources.items() if descriptor.get("present") is True
    }
    if listed_paths != present_paths:
        raise MemoryBackupError("Backup manifest source presence does not match archive files")


def _read_and_verify_archive(archive_path: Union[str, Path]) -> Tuple[Dict, Dict[str, bytes], Dict]:
    path = Path(archive_path).expanduser()
    if not path.is_file():
        raise MemoryBackupError(f"Backup archive does not exist: {path}")
    try:
        with zipfile.ZipFile(path, "r") as archive:
            names = archive.namelist()
            if len(names) != len(set(names)):
                raise MemoryBackupError("Backup archive contains duplicate entries")
            if MANIFEST_PATH not in names:
                raise MemoryBackupError("Backup archive is missing its manifest")
            manifest = _json_object(archive.read(MANIFEST_PATH), "backup manifest")
            if (
                manifest.get("schema_version") not in SUPPORTED_BACKUP_SCHEMA_VERSIONS
                or manifest.get("format") != BACKUP_FORMAT
            ):
                raise MemoryBackupError("Unsupported backup manifest")
            entries = manifest.get("files")
            if not isinstance(entries, list) or not entries:
                raise MemoryBackupError("Backup manifest has no file inventory")

            listed_paths = []
            payloads = {}
            for entry in entries:
                if not isinstance(entry, dict):
                    raise MemoryBackupError("Backup manifest contains an invalid file entry")
                member = entry.get("path")
                if not isinstance(member, str) or not _expected_archive_path(member):
                    raise MemoryBackupError("Backup manifest contains an unsafe file path")
                if member in listed_paths:
                    raise MemoryBackupError("Backup manifest contains duplicate file paths")
                listed_paths.append(member)
                if member not in names:
                    raise MemoryBackupError(f"Backup archive is missing {member}")
                info = archive.getinfo(member)
                expected_size = entry.get("bytes")
                if not isinstance(expected_size, int) or expected_size < 0 or info.file_size != expected_size:
                    raise MemoryBackupError(f"Backup size mismatch for {member}")
                payload = archive.read(member)
                if entry.get("sha256") != _sha256(payload):
                    raise MemoryBackupError(f"Backup checksum mismatch for {member}")
                payloads[member] = payload

            if set(names) != {MANIFEST_PATH, *listed_paths}:
                raise MemoryBackupError("Backup archive contains unmanifested entries")
    except (OSError, zipfile.BadZipFile) as exc:
        raise MemoryBackupError(f"Cannot read backup archive: {path}") from exc

    snapshot = _validate_snapshot(payloads)
    canonical_meta = manifest.get("canonical")
    if not isinstance(canonical_meta, dict):
        raise MemoryBackupError("Backup manifest has no canonical metadata")
    if (
        canonical_meta.get("schema_version") != snapshot["canonical"]["schema_version"]
        or canonical_meta.get("revision") != int(snapshot["canonical"]["revision"])
        or canonical_meta.get("memory_count") != len(snapshot["memory_ids"])
        or canonical_meta.get("project_count") != len(snapshot["project_ids"])
    ):
        raise MemoryBackupError("Backup manifest does not match canonical memory")
    migration = manifest.get("migration")
    if not isinstance(migration, dict) or migration.get("name") != "scope-v2":
        raise MemoryBackupError("Backup manifest has invalid migration metadata")
    if manifest["schema_version"] >= 2:
        state_meta = manifest.get("state")
        if not isinstance(state_meta, dict):
            raise MemoryBackupError("Backup manifest has no project state metadata")
        state = snapshot["state"]
        if (
            state_meta.get("schema_version") != (state["schema_version"] if state else None)
            or state_meta.get("project_count") != (len(state["projects"]) if state else 0)
        ):
            raise MemoryBackupError("Backup manifest does not match canonical project state")
    if manifest["schema_version"] >= 3:
        _verify_schema3_snapshot(manifest, payloads)
    return manifest, payloads, snapshot


def create_backup(vault_path: Union[str, Path], archive_path: Union[str, Path]) -> Dict:
    """Write a verified backup of canonical authorities, excluding projections."""
    payloads, snapshot, descriptors, attempts = _stable_source_snapshot(vault_path)
    output = Path(archive_path).expanduser()
    if output.exists():
        raise MemoryBackupError(f"Refusing to overwrite an existing backup: {output}")
    _atomic_create_archive(output, _manifest_for(payloads, snapshot, descriptors, attempts), payloads)
    manifest, _verified_payloads, _verified_snapshot = _read_and_verify_archive(output)
    return {
        "status": "created",
        "archive": str(output),
        "archive_id": manifest["archive_id"],
        "canonical_revision": manifest["canonical"]["revision"],
        "memory_count": manifest["canonical"]["memory_count"],
        "project_count": manifest["canonical"]["project_count"],
        "state_project_count": manifest.get("state", {}).get("project_count", 0),
    }


def verify_backup(archive_path: Union[str, Path]) -> Dict:
    """Validate a backup archive and return evidence without extracting it."""
    manifest, _payloads, _snapshot = _read_and_verify_archive(archive_path)
    return {
        "status": "verified",
        "archive": str(Path(archive_path).expanduser()),
        "archive_id": manifest["archive_id"],
        "canonical_revision": manifest["canonical"]["revision"],
        "memory_count": manifest["canonical"]["memory_count"],
        "project_count": manifest["canonical"]["project_count"],
        "state_project_count": manifest.get("state", {}).get("project_count", 0),
    }


def _restored_target_matches(vault: Path, payloads: Dict[str, bytes]) -> bool:
    return all(
        (vault / target).is_file() and (vault / target).read_bytes() == payload
        for archive_path, payload in payloads.items()
        for target in (RESTORE_PATHS[archive_path],)
    )


def restore_backup(archive_path: Union[str, Path], vault_path: Union[str, Path]) -> Dict:
    """Restore only into a new blank vault; never overwrite user data."""
    manifest, payloads, _snapshot = _read_and_verify_archive(archive_path)
    vault = Path(vault_path).expanduser()
    if vault.is_symlink():
        raise MemoryBackupError(f"Restore target must not be a symbolic link: {vault}")
    if vault.exists():
        if _restored_target_matches(vault, payloads):
            return {
                "status": "already_restored",
                "vault": str(vault),
                "canonical_revision": manifest["canonical"]["revision"],
            }
        raise MemoryBackupError(
            f"Restore target must not exist unless it already matches this backup: {vault}"
        )

    vault.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".memory-restore-", dir=vault.parent))
    try:
        for archive_member, payload in payloads.items():
            destination = staging / RESTORE_PATHS[archive_member]
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(payload)
        # Validate the staged copy before it becomes visible as a vault.
        _read_source_payloads(staging)
        staging.replace(vault)
    except OSError as exc:
        raise MemoryBackupError(f"Cannot restore backup into {vault}") from exc
    finally:
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)

    return {
        "status": "restored",
        "vault": str(vault),
        "canonical_revision": manifest["canonical"]["revision"],
        "memory_count": manifest["canonical"]["memory_count"],
        "project_count": manifest["canonical"]["project_count"],
        "state_project_count": manifest.get("state", {}).get("project_count", 0),
    }


def _load_context_compiler():
    script = Path(__file__).with_name("context-compiler.py")
    spec = importlib.util.spec_from_file_location("brain_eleven_context_compiler", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.ContextCompiler


def run_disaster_drill(
    vault_path: Union[str, Path], archive_path: Union[str, Path], project_id: Optional[str] = None
) -> Dict:
    """Prove a backup restores into a blank environment and rebuilds projections."""
    created = create_backup(vault_path, archive_path)
    with tempfile.TemporaryDirectory(prefix="brain-eleven-restore-drill-") as temporary_root:
        restored_vault = Path(temporary_root) / "restored-vault"
        restored = restore_backup(archive_path, restored_vault)
        document = MemoryStore(restored_vault).load()
        restored_state = StateStore(restored_vault).load()
        source_ids = {
            memory["memory_id"]
            for bucket in ("validated_memory", "rejected_memory")
            for memory in document[bucket]
        }
        graph = EntityExtractor(str(restored_vault)).build_graph()
        ContextCompiler = _load_context_compiler()
        compiler = ContextCompiler(str(restored_vault), project_id=project_id)
        compiler.save()
        selected_ids = {
            memory["memory_id"] for memory in compiler._rank_memories(limit=5)
        }
        other_project_ids = {
            memory["memory_id"]
            for memory in document["validated_memory"]
            if infer_memory_scope(memory)[0] == PROJECT_SCOPE
            and infer_memory_scope(memory)[2] != project_id
        }
        leakage = sorted(selected_ids & other_project_ids)
        bootstrap = compiler.bootstrap_status()

        if graph.projection_status()["status"] != "fresh":
            raise MemoryBackupError("Graph rebuild did not produce a fresh projection")
        if bootstrap["status"] != "fresh":
            raise MemoryBackupError("Context rebuild did not produce a fresh bootstrap")
        if leakage:
            raise MemoryBackupError("Disaster drill detected wrong-project context leakage")

    return {
        "status": "passed",
        "backup": created,
        "restore": restored,
        "canonical_revision": int(document["revision"]),
        "memory_ids": sorted(source_ids),
        "selected_memory_ids": sorted(selected_ids),
        "wrong_project_leakage": 0,
        "state_project_ids": sorted(restored_state["projects"]),
    }


def main(argv: Optional[Iterable[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Backup and restore Brain-Eleven canonical memory")
    commands = parser.add_subparsers(dest="command", required=True)

    create = commands.add_parser("create", help="Create a verified canonical-memory ZIP")
    create.add_argument("--vault", default=".")
    create.add_argument("--output", required=True)

    verify = commands.add_parser("verify", help="Verify a backup ZIP without extracting it")
    verify.add_argument("--archive", required=True)

    restore = commands.add_parser("restore", help="Restore a ZIP only into a new blank vault")
    restore.add_argument("--archive", required=True)
    restore.add_argument("--vault", required=True)

    drill = commands.add_parser("drill", help="Backup, blank-restore, and rebuild derived state")
    drill.add_argument("--vault", default=".")
    drill.add_argument("--output", required=True)
    drill.add_argument("--project-id", default=None)

    args = parser.parse_args(argv)
    try:
        if args.command == "create":
            result = create_backup(args.vault, args.output)
        elif args.command == "verify":
            result = verify_backup(args.archive)
        elif args.command == "restore":
            result = restore_backup(args.archive, args.vault)
        else:
            result = run_disaster_drill(args.vault, args.output, args.project_id)
    except (MemoryBackupError, MemoryStoreCorrupt, ProjectRegistryError, OSError) as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}, ensure_ascii=False))
        return 2

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
