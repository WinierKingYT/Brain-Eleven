"""Content-free derived cache for compiler selection audit metadata."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Mapping, Optional


class CompilerCache:
    """A corrupt cache is ignored; canonical inputs are always revalidated."""

    relative_path = Path(".claude") / "context-compiler-v2-cache.json"

    def __init__(self, vault_path: str | Path):
        self.path = Path(vault_path) / self.relative_path

    @staticmethod
    def _content_safe(value: Any) -> bool:
        if isinstance(value, Mapping):
            return "content" not in value and "rendered_context" not in value and all(
                CompilerCache._content_safe(item) for item in value.values()
            )
        if isinstance(value, list):
            return all(CompilerCache._content_safe(item) for item in value)
        return True

    def load(self, key: str, revisions: Mapping[str, Any]) -> Optional[Mapping[str, Any]]:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return None
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
        return manifest

    def store(self, key: str, revisions: Mapping[str, Any], manifest: Mapping[str, Any]) -> None:
        if not self._content_safe(manifest):
            raise ValueError("Compiler cache refuses context content")
        entries: dict[str, Any] = {}
        existing = self.load_all()
        if isinstance(existing, Mapping):
            entries.update(existing)
        entries[key] = {"revisions": dict(revisions), "manifest": dict(manifest)}
        # Keep derived cache bounded and deterministic.
        entries = dict(sorted(entries.items())[-32:])
        self.path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(prefix=".compiler-cache-", suffix=".json", dir=self.path.parent)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
                json.dump({"schema_version": 1, "entries": entries}, handle, ensure_ascii=False, sort_keys=True)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def load_all(self) -> Optional[Mapping[str, Any]]:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return None
        entries = payload.get("entries") if isinstance(payload, Mapping) else None
        return entries if isinstance(entries, Mapping) else None
