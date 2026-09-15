"""Content-free derived cache for compiler selection audit metadata."""

from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any, Mapping, Optional

from brain_eleven.infrastructure.locking import file_lock


class CompilerCache:
    """A corrupt cache is ignored; canonical inputs are always revalidated."""

    relative_path = Path(".claude") / "context-compiler-v2-cache.json"

    def __init__(self, vault_path: str | Path):
        self.path = Path(vault_path) / self.relative_path

    @staticmethod
    def _content_safe(value: Any) -> bool:
        if isinstance(value, Mapping):
            forbidden_keys = {
                "content", "rendered_context", "rendered_text", "raw_request", "prompt", "text"
            }
            if any(str(key).casefold() in forbidden_keys for key in value):
                return False
            return all(
                CompilerCache._content_safe(item) for item in value.values()
            )
        if isinstance(value, list):
            return all(CompilerCache._content_safe(item) for item in value)
        return True

    def load(self, key: str, revisions: Mapping[str, Any]) -> Optional[Mapping[str, Any]]:
        try:
            with file_lock(self.path):
                if not self.path.exists():
                    return None
                payload = json.loads(self.path.read_text(encoding="utf-8"))
                if not isinstance(payload, Mapping) or payload.get("schema_version") != 1:
                    return None
                entries = payload.get("entries")
                if not isinstance(entries, Mapping):
                    return None
                value = entries.get(key)
                if not isinstance(value, Mapping) or value.get("revisions") != dict(revisions):
                    return None
                manifest = value.get("manifest")
                if not isinstance(manifest, Mapping) or not self._content_safe(manifest):
                    return None
                value["last_access_ns"] = time.time_ns()
                try:
                    self._write_unlocked(payload)
                except OSError:
                    pass
                return manifest
        except (OSError, TimeoutError, UnicodeDecodeError, json.JSONDecodeError):
            return None

    def store(self, key: str, revisions: Mapping[str, Any], manifest: Mapping[str, Any]) -> None:
        if not self._content_safe(manifest):
            raise ValueError("Compiler cache refuses context content")
        try:
            with file_lock(self.path):
                entries: dict[str, Any] = {}
                existing = self._load_all_unlocked()
                if isinstance(existing, Mapping):
                    entries.update(existing)
                entries[key] = {"revisions": dict(revisions), "manifest": dict(manifest), "last_access_ns": time.time_ns()}
                # Keep derived cache bounded by least-recently-used access, not key
                # spelling. The cache is an audit projection, never canonical truth.
                if len(entries) > 32:
                    stale = sorted(entries, key=lambda item: (entries[item].get("last_access_ns", 0), item))[:-32]
                    for stale_key in stale:
                        entries.pop(stale_key, None)
                self._write_unlocked({"schema_version": 1, "entries": entries})
        except (OSError, TimeoutError):
            return

    def _write_unlocked(self, payload: Mapping[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(prefix=".compiler-cache-", suffix=".json", dir=self.path.parent)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
                json.dump(payload, handle, ensure_ascii=False, sort_keys=True)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def load_all(self) -> Optional[Mapping[str, Any]]:
        try:
            with file_lock(self.path):
                return self._load_all_unlocked()
        except (OSError, TimeoutError, UnicodeDecodeError, json.JSONDecodeError):
            return None

    def _load_all_unlocked(self) -> Optional[Mapping[str, Any]]:
        if not self.path.exists():
            return None
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        entries = payload.get("entries") if isinstance(payload, Mapping) else None
        return entries if isinstance(entries, Mapping) else None
