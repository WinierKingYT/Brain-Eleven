"""Derived, privacy-safe RouterResult cache."""

from __future__ import annotations

from contextvars import ContextVar
import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any, Mapping, Optional

from brain_eleven.infrastructure.locking import file_lock


CACHE_SCHEMA_VERSION = 1
_ACCESS_REFRESH_ENABLED = ContextVar("router_cache_access_refresh_enabled", default=True)


class RouterCache:
    def __init__(self, vault_path: str | Path):
        self.path = Path(vault_path) / ".claude" / "context-router-cache.json"

    def load(self, key: str, revisions: Mapping[str, Any]) -> Optional[dict[str, Any]]:
        try:
            with file_lock(self.path):
                loaded = self._read_entry_unlocked(key, revisions)
                if loaded is None:
                    return None
                document, entry, result = loaded
                if _ACCESS_REFRESH_ENABLED.get():
                    entry["last_access_ns"] = time.time_ns()
                    try:
                        self._write_unlocked(document)
                    except OSError:
                        pass
                return result
        except (OSError, TimeoutError, json.JSONDecodeError):
            return None

    def load_read_only(self, key: str, revisions: Mapping[str, Any]) -> Optional[dict[str, Any]]:
        """Load a hit without refreshing bytes before the caller validates lineage."""
        token = _ACCESS_REFRESH_ENABLED.set(False)
        try:
            return self.load(key, revisions)
        finally:
            _ACCESS_REFRESH_ENABLED.reset(token)

    def touch(self, key: str, revisions: Mapping[str, Any]) -> None:
        """Refresh access metadata after the caller validates its input."""
        try:
            with file_lock(self.path):
                loaded = self._read_entry_unlocked(key, revisions)
                if loaded is None:
                    return
                document, entry, _result = loaded
                entry["last_access_ns"] = time.time_ns()
                try:
                    self._write_unlocked(document)
                except OSError:
                    pass
        except (OSError, TimeoutError, json.JSONDecodeError):
            return

    def _read_entry_unlocked(
        self, key: str, revisions: Mapping[str, Any]
    ) -> Optional[tuple[dict[str, Any], dict[str, Any], dict[str, Any]]]:
        if not self.path.exists():
            return None
        document = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(document, dict) or document.get("schema_version") != CACHE_SCHEMA_VERSION:
            return None
        entry = document.get("entries", {}).get(key)
        if not isinstance(entry, dict) or entry.get("input_revisions") != dict(revisions):
            return None
        result = entry.get("result")
        if not isinstance(result, dict):
            return None
        return document, entry, result

    def store(self, key: str, revisions: Mapping[str, Any], result: Mapping[str, Any]) -> None:
        try:
            with file_lock(self.path):
                document: dict[str, Any] = {"schema_version": CACHE_SCHEMA_VERSION, "entries": {}}
                if self.path.exists():
                    try:
                        existing = json.loads(self.path.read_text(encoding="utf-8"))
                        if isinstance(existing, dict) and existing.get("schema_version") == CACHE_SCHEMA_VERSION:
                            document = existing
                    except (OSError, json.JSONDecodeError):
                        pass
                entries = document.setdefault("entries", {})
                entries[key] = {"input_revisions": dict(revisions), "result": dict(result), "last_access_ns": time.time_ns()}
                # Bound derived state; cache is never canonical authority.
                if len(entries) > 32:
                    stale = sorted(entries, key=lambda item: (entries[item].get("last_access_ns", 0), item))[:-32]
                    for stale_key in stale:
                        entries.pop(stale_key, None)
                self._write_unlocked(document)
        except (OSError, TimeoutError):
            return

    def _write_unlocked(self, document: Mapping[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(prefix=".context-router-cache-", suffix=".json", dir=self.path.parent)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(document, handle, ensure_ascii=False, indent=2)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            Path(temporary).replace(self.path)
        finally:
            candidate = Path(temporary)
            if candidate.exists():
                candidate.unlink()
