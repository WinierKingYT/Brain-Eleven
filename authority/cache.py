"""Derived, content-free cache for authority outputs."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Mapping, Optional


CACHE_SCHEMA_VERSION = 1


class AuthorityCache:
    def __init__(self, vault_path: str | Path):
        self.path = Path(vault_path) / ".claude" / "authority-cache.json"

    def load(self, key: str, revisions: Mapping[str, Any]) -> Optional[dict[str, Any]]:
        if not self.path.exists():
            return None
        try:
            document = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if not isinstance(document, dict) or document.get("schema_version") != CACHE_SCHEMA_VERSION:
            return None
        entry = document.get("entries", {}).get(key)
        if not isinstance(entry, dict) or entry.get("input_revisions") != dict(revisions):
            return None
        result = entry.get("result")
        return result if isinstance(result, dict) else None

    def store(self, key: str, revisions: Mapping[str, Any], result: Mapping[str, Any]) -> None:
        """Persist bounded derived state. Cache failures never affect authority truth."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        document: dict[str, Any] = {"schema_version": CACHE_SCHEMA_VERSION, "entries": {}}
        if self.path.exists():
            try:
                existing = json.loads(self.path.read_text(encoding="utf-8"))
                if isinstance(existing, dict) and existing.get("schema_version") == CACHE_SCHEMA_VERSION:
                    document = existing
            except (OSError, json.JSONDecodeError):
                pass
        entries = document.setdefault("entries", {})
        entries[key] = {"input_revisions": dict(revisions), "result": dict(result)}
        if len(entries) > 32:
            for stale_key in sorted(entries)[:-32]:
                entries.pop(stale_key, None)
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
