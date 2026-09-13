"""Content-free ownership checks for native transcript capture.

The queue event is the authority for session and project identity.  Native
transcript metadata can only confirm that identity; it can never replace it.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
from typing import Any

from brain_eleven.projects.registry import ProjectRegistry, normalize_registry_root


MAX_TRANSCRIPT_BYTES = 128 * 1024 * 1024


class TranscriptOwnershipError(ValueError):
    """A bounded, content-free ownership or stable-source failure."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class TranscriptBinding:
    """Validated identity and content token for one read attempt."""

    path: Path
    client: str
    session_key: str
    project_id: str
    project_root: str
    content_sha256: str
    file_identity: tuple[int, int, int, int]


def session_key(client: str, raw_session_id: str) -> str:
    if client not in {"claude", "codex"} or not isinstance(raw_session_id, str) or not raw_session_id:
        raise TranscriptOwnershipError("TRANSCRIPT_OWNERSHIP_UNVERIFIED")
    return client + ":" + hashlib.sha256(raw_session_id.encode("utf-8")).hexdigest()


def _file_identity(stat_result: Any) -> tuple[int, int, int, int]:
    return (
        int(getattr(stat_result, "st_dev", 0)),
        int(getattr(stat_result, "st_ino", 0)),
        int(stat_result.st_size),
        int(getattr(stat_result, "st_mtime_ns", 0)),
    )


def _project_slug(project_root: str) -> str:
    normalized = str(Path(project_root).expanduser().resolve(strict=False))
    return normalized.replace(":", "-").replace("/", "-").replace("\\", "-")


def _hash_normalized(client: str, value: Any) -> str | None:
    return session_key(client, value) if isinstance(value, str) and value else None


def _read_native_metadata(path: Path, client: str) -> tuple[list[str], list[str], str]:
    """Read bounded native metadata and return identities plus source digest."""
    try:
        with path.open("rb") as handle:
            before = _file_identity(os.fstat(handle.fileno()))
            raw = handle.read(MAX_TRANSCRIPT_BYTES + 1)
            after_handle = _file_identity(os.fstat(handle.fileno()))
        after_path = _file_identity(path.stat())
    except FileNotFoundError as exc:
        raise TranscriptOwnershipError("TRANSCRIPT_NOT_FOUND") from exc
    except OSError as exc:
        raise TranscriptOwnershipError("TRANSCRIPT_NOT_FOUND") from exc
    if len(raw) > MAX_TRANSCRIPT_BYTES:
        raise TranscriptOwnershipError("TRANSCRIPT_CHANGED")
    if before != after_handle or before != after_path:
        raise TranscriptOwnershipError("TRANSCRIPT_CHANGED")

    session_values: list[str] = []
    project_values: list[str] = []
    try:
        lines = raw.decode("utf-8").splitlines()
    except UnicodeDecodeError as exc:
        raise TranscriptOwnershipError("TRANSCRIPT_OWNERSHIP_UNVERIFIED") from exc
    for line in lines:
        if not line.strip():
            continue
        try:
            document = json.loads(line)
        except json.JSONDecodeError as exc:
            raise TranscriptOwnershipError("TRANSCRIPT_OWNERSHIP_UNVERIFIED") from exc
        if not isinstance(document, dict):
            continue
        if client == "claude":
            value = document.get("sessionId")
            if isinstance(value, str) and value:
                session_values.append(value)
        else:
            if document.get("type") != "session_meta":
                continue
            payload = document.get("payload")
            if not isinstance(payload, dict):
                continue
            value = payload.get("session_id")
            cwd = payload.get("cwd")
            if isinstance(value, str) and value:
                session_values.append(value)
            if isinstance(cwd, str) and cwd:
                project_values.append(cwd)
    return session_values, project_values, hashlib.sha256(raw).hexdigest()


def verify_transcript_ownership(
    vault: str | Path,
    path: str | Path,
    client: str,
    expected_session_key: str,
    project_id: str,
    project_root: str,
) -> TranscriptBinding:
    """Confirm native session/project metadata without reading message content."""
    if client not in {"claude", "codex"}:
        raise TranscriptOwnershipError("TRANSCRIPT_OWNERSHIP_UNVERIFIED")
    if not isinstance(expected_session_key, str) or not expected_session_key.startswith(client + ":"):
        raise TranscriptOwnershipError("TRANSCRIPT_OWNERSHIP_UNVERIFIED")
    try:
        resolved = Path(path).expanduser().resolve(strict=True)
        if Path(path).expanduser().is_symlink() or not resolved.is_file():
            raise TranscriptOwnershipError("TRANSCRIPT_OWNERSHIP_UNVERIFIED")
    except TranscriptOwnershipError:
        raise
    except (OSError, RuntimeError) as exc:
        raise TranscriptOwnershipError("TRANSCRIPT_NOT_FOUND") from exc

    expected_root = normalize_registry_root(project_root)
    registry = ProjectRegistry(vault)
    record = registry.get(project_id)
    if not record or record.get("root") != expected_root:
        raise TranscriptOwnershipError("TRANSCRIPT_OWNERSHIP_MISMATCH")
    if client == "claude":
        matching_roots = [
            item for item in registry.list_projects()
            if _project_slug(str(item.get("root", ""))) == resolved.parent.name
        ]
        if len(matching_roots) != 1:
            raise TranscriptOwnershipError("TRANSCRIPT_OWNERSHIP_UNVERIFIED")
        if matching_roots[0].get("project_id") != project_id:
            raise TranscriptOwnershipError("TRANSCRIPT_OWNERSHIP_MISMATCH")
        if _project_slug(expected_root) != resolved.parent.name:
            raise TranscriptOwnershipError("TRANSCRIPT_OWNERSHIP_MISMATCH")
        if _hash_normalized(client, resolved.stem) != expected_session_key:
            raise TranscriptOwnershipError("TRANSCRIPT_OWNERSHIP_MISMATCH")

    session_values, project_values, digest = _read_native_metadata(resolved, client)
    normalized_sessions = {_hash_normalized(client, value) for value in session_values}
    normalized_sessions.discard(None)
    if not normalized_sessions:
        raise TranscriptOwnershipError("TRANSCRIPT_OWNERSHIP_UNVERIFIED")
    if normalized_sessions != {expected_session_key}:
        raise TranscriptOwnershipError("TRANSCRIPT_OWNERSHIP_MISMATCH")
    if client == "codex":
        normalized_projects = {normalize_registry_root(value) for value in project_values}
        if not normalized_projects:
            raise TranscriptOwnershipError("TRANSCRIPT_OWNERSHIP_UNVERIFIED")
        if normalized_projects != {expected_root}:
            raise TranscriptOwnershipError("TRANSCRIPT_OWNERSHIP_MISMATCH")
    return TranscriptBinding(
        path=resolved,
        client=client,
        session_key=expected_session_key,
        project_id=project_id,
        project_root=expected_root,
        content_sha256=digest,
        file_identity=_file_identity(resolved.stat()),
    )
