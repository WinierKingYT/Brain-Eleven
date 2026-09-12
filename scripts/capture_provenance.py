"""Trusted transcript-root resolution for the native capture boundary.

Hook payloads may carry an absolute transcript locator, but that locator is
still untrusted data. This module confines it to an operator-configured client
root before queueing or reading evidence. It deliberately does not claim
project/session ownership; those checks belong to a later provenance package.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable

from brain_eleven.runtime.storage import RuntimeConfig


class TranscriptProvenanceError(ValueError):
    """Content-free failure raised when a transcript path is not trusted."""

    code = "TRANSCRIPT_PROVENANCE_INVALID"

    def __init__(self, code: str, message: str = "transcript provenance is invalid"):
        self.code = code
        super().__init__(message)


def _native_roots(client: str) -> tuple[Path, ...]:
    if client == "claude":
        return (Path.home() / ".claude" / "projects",)
    if client == "codex":
        codex_home = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex")))
        return (codex_home / "sessions",)
    raise TranscriptProvenanceError("TRANSCRIPT_PROVENANCE_CLIENT", "unsupported transcript client")


def _configured_roots(vault: str | Path, client: str) -> tuple[Path, ...]:
    config = RuntimeConfig(vault).load()
    configured = config.get("transcript_roots")
    if configured is None:
        raw_roots: Iterable[object] = _native_roots(client)
    else:
        if not isinstance(configured, dict):
            raise TranscriptProvenanceError("TRANSCRIPT_PROVENANCE_CONFIG", "transcript roots configuration is invalid")
        raw_roots = configured.get(client, ())
        if not isinstance(raw_roots, list) or not raw_roots:
            raise TranscriptProvenanceError("TRANSCRIPT_PROVENANCE_ROOT", "transcript root is not configured")

    roots: list[Path] = []
    for raw_root in raw_roots:
        if isinstance(raw_root, Path):
            root = raw_root
        elif isinstance(raw_root, str) and raw_root:
            root = Path(raw_root)
        else:
            raise TranscriptProvenanceError("TRANSCRIPT_PROVENANCE_ROOT", "transcript root is invalid")
        if not root.is_absolute() or ".." in root.parts:
            raise TranscriptProvenanceError("TRANSCRIPT_PROVENANCE_ROOT", "transcript root must be absolute")
        try:
            resolved = root.expanduser().resolve(strict=True)
        except (OSError, RuntimeError) as exc:
            raise TranscriptProvenanceError("TRANSCRIPT_PROVENANCE_ROOT", "transcript root is unavailable") from exc
        if not resolved.is_dir():
            raise TranscriptProvenanceError("TRANSCRIPT_PROVENANCE_ROOT", "transcript root is not a directory")
        roots.append(resolved)
    return tuple(roots)


def resolve_transcript_path(vault: str | Path, client: str, source: str | Path) -> Path:
    """Return a canonical transcript path only when it is root-confined."""
    if client not in {"claude", "codex"}:
        raise TranscriptProvenanceError("TRANSCRIPT_PROVENANCE_CLIENT", "unsupported transcript client")
    if not isinstance(source, (str, Path)) or not str(source) or "\x00" in str(source):
        raise TranscriptProvenanceError("TRANSCRIPT_PROVENANCE_PATH", "transcript path is invalid")
    original = Path(source).expanduser()
    if not original.is_absolute() or ".." in original.parts:
        raise TranscriptProvenanceError("TRANSCRIPT_PROVENANCE_PATH", "transcript path must be absolute")
    try:
        if original.is_symlink():
            raise TranscriptProvenanceError("TRANSCRIPT_PROVENANCE_SYMLINK", "transcript path must not be a symlink")
        resolved = original.resolve(strict=True)
    except TranscriptProvenanceError:
        raise
    except (OSError, RuntimeError) as exc:
        raise TranscriptProvenanceError("TRANSCRIPT_PROVENANCE_MISSING", "transcript source is unavailable") from exc
    if not resolved.is_file():
        raise TranscriptProvenanceError("TRANSCRIPT_PROVENANCE_FILE", "transcript source is not a regular file")
    for root in _configured_roots(vault, client):
        try:
            resolved.relative_to(root)
        except ValueError:
            continue
        return resolved
    raise TranscriptProvenanceError("TRANSCRIPT_PROVENANCE_SCOPE", "transcript source is outside the trusted client root")
