"""Derived, content-free cache for authority outputs."""

from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any, Mapping, Optional

from brain_eleven.infrastructure.locking import file_lock


CACHE_SCHEMA_VERSION = 1


class AuthorityCache:
    def __init__(self, vault_path: str | Path):
        self.path = Path(vault_path) / ".claude" / "authority-cache.json"

    def load(self, key: str, revisions: Mapping[str, Any]) -> Optional[dict[str, Any]]:
        try:
            with file_lock(self.path):
                if not self.path.exists():
                    return None
                try:
                    document = json.loads(self.path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError, UnicodeDecodeError):
                    return None
                if not isinstance(document, dict) or document.get("schema_version") != CACHE_SCHEMA_VERSION:
                    return None
                entries = document.get("entries")
                if not isinstance(entries, dict):
                    return None
                entry = entries.get(key)
                if not isinstance(entry, dict) or entry.get("input_revisions") != dict(revisions):
                    return None
                result = entry.get("result")
                if not isinstance(result, dict):
                    return None
                entry["last_access_ns"] = time.time_ns()
                try:
                    self._write_unlocked(document)
                except OSError:
                    pass
                return result
        except (OSError, TimeoutError, json.JSONDecodeError, UnicodeDecodeError):
            return None

    def store(self, key: str, revisions: Mapping[str, Any], result: Mapping[str, Any]) -> None:
        """Persist bounded derived state. Cache failures never affect authority truth."""
        try:
            with file_lock(self.path):
                self.path.parent.mkdir(parents=True, exist_ok=True)
                document: dict[str, Any] = {"schema_version": CACHE_SCHEMA_VERSION, "entries": {}}
                if self.path.exists():
                    try:
                        existing = json.loads(self.path.read_text(encoding="utf-8"))
                        if isinstance(existing, dict) and existing.get("schema_version") == CACHE_SCHEMA_VERSION:
                            document = existing
                    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
                        pass
                entries = document.get("entries")
                if not isinstance(entries, dict):
                    entries = {}
                    document["entries"] = entries
                entries[key] = {
                    "input_revisions": dict(revisions),
                    "result": dict(result),
                    "last_access_ns": time.time_ns(),
                }
                if len(entries) > 32:
                    stale = sorted(entries, key=lambda item: (entries[item].get("last_access_ns", 0), item))[:-32]
                    for stale_key in stale:
                        entries.pop(stale_key, None)
                self._write_unlocked(document)
        except TimeoutError:
            return

    def _write_unlocked(self, document: Mapping[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(prefix=".authority-cache-", suffix=".json", dir=self.path.parent)
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
