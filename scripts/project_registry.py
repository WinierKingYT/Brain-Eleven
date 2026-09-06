#!/usr/bin/env python3
"""Vault-local registry for stable cross-project identities.

The canonical memory records deliberately do not contain filesystem paths.
This small registry is the local-only mapping that lets a project keep the
same opaque identity when its directory is moved or renamed.
"""

import json
import os
import secrets
import tempfile
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Union

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

try:
    from brain_eleven.infrastructure.locking import file_lock  # noqa: E402
except ModuleNotFoundError as exc:  # pragma: no cover - copied-hook fallback
    if exc.name != "brain_eleven":
        raise
    from memory_store_lock import file_lock  # noqa: E402


REGISTRY_SCHEMA_VERSION = 1
REGISTRY_FILENAME = "project-registry.json"
VALID_STATUSES = {"active", "archived"}


class ProjectRegistryError(ValueError):
    """Raised when the local project registry is invalid or inconsistent."""


def registry_path(vault_path: Union[str, Path]) -> Path:
    """Return the ignored, vault-local registry path."""
    return Path(vault_path).expanduser() / ".claude" / REGISTRY_FILENAME


def normalize_registry_root(project_root: Union[str, Path]) -> str:
    """Normalize a root using the host filesystem's case semantics."""
    root = Path(project_root).expanduser().resolve(strict=False)
    return os.path.normcase(os.path.normpath(str(root)))


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _atomic_write(path: Path, data: Dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=".project-registry-", suffix=".json", dir=path.parent
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
        Path(temporary_name).replace(path)
    finally:
        temporary = Path(temporary_name)
        if temporary.exists():
            temporary.unlink()


def _empty_registry() -> Dict:
    return {
        "schema_version": REGISTRY_SCHEMA_VERSION,
        "updated_at": _utc_now(),
        "projects": [],
    }


class ProjectRegistry:
    """Manage stable project identities without putting roots in memories."""

    def __init__(self, vault_path: Union[str, Path]):
        candidate = Path(vault_path).expanduser()
        self.path = candidate if candidate.name == REGISTRY_FILENAME else registry_path(candidate)

    def load(self) -> Dict:
        """Load and validate the registry; corruption is never treated as empty."""
        if not self.path.exists():
            return _empty_registry()
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ProjectRegistryError(f"Cannot read project registry: {self.path}") from exc
        self._validate(data)
        return data

    @staticmethod
    def _validate(data: Dict) -> None:
        if not isinstance(data, dict) or data.get("schema_version") != REGISTRY_SCHEMA_VERSION:
            raise ProjectRegistryError("Unsupported project registry schema")
        projects = data.get("projects")
        if not isinstance(projects, list):
            raise ProjectRegistryError("Project registry projects must be a list")
        seen_ids = set()
        seen_roots = set()
        for project in projects:
            if not isinstance(project, dict):
                raise ProjectRegistryError("Project registry contains a non-object project")
            project_id = str(project.get("project_id") or "").strip()
            root = str(project.get("root") or "").strip()
            status = project.get("status", "active")
            if not project_id or not root or project_id in seen_ids or root in seen_roots:
                raise ProjectRegistryError("Project registry contains duplicate or incomplete identity")
            if status not in VALID_STATUSES:
                raise ProjectRegistryError(f"Unsupported project status: {status}")
            if not isinstance(project.get("proactive_capture", False), bool):
                raise ProjectRegistryError("proactive_capture must be boolean")
            seen_ids.add(project_id)
            seen_roots.add(root)

    def _mutate(self, callback):
        with file_lock(self.path):
            data = self.load()
            result = callback(data)
            data["updated_at"] = _utc_now()
            self._validate(data)
            _atomic_write(self.path, data)
            return result

    def list_projects(self) -> List[Dict]:
        return [dict(project) for project in self.load()["projects"]]

    def get(self, project_id: str) -> Optional[Dict]:
        project_id = str(project_id or "").strip()
        return next(
            (dict(project) for project in self.load()["projects"] if project.get("project_id") == project_id),
            None,
        )

    def resolve(self, project_root: Union[str, Path]) -> Optional[Dict]:
        normalized_root = normalize_registry_root(project_root)
        return next(
            (dict(project) for project in self.load()["projects"] if project.get("root") == normalized_root),
            None,
        )

    def proactive_capture_policy(self, project_root: Union[str, Path]) -> Dict:
        """Return the canonical, fail-closed proactive-capture decision."""
        record = self.resolve(project_root)
        if record is None:
            return {"allowed": False, "reason": "unregistered", "project_id": None}
        if record["status"] != "active":
            return {
                "allowed": False,
                "reason": "archived",
                "project_id": record["project_id"],
            }
        if not record["proactive_capture"]:
            return {
                "allowed": False,
                "reason": "disabled",
                "project_id": record["project_id"],
            }
        return {"allowed": True, "reason": "enabled", "project_id": record["project_id"]}

    def register(
        self,
        project_root: Union[str, Path],
        project_label: Optional[str] = None,
        project_id: Optional[str] = None,
        status: str = "active",
        proactive_capture: bool = False,
    ) -> Dict:
        """Register or return a project identity, rejecting conflicting IDs."""
        normalized_root = normalize_registry_root(project_root)
        label = str(project_label or Path(normalized_root).name or normalized_root).strip()
        if status not in VALID_STATUSES:
            raise ProjectRegistryError(f"Unsupported project status: {status}")
        if proactive_capture and status != "active":
            raise ProjectRegistryError("Archived projects cannot enable proactive capture")

        def mutate(data):
            projects = data["projects"]
            by_root = next((item for item in projects if item["root"] == normalized_root), None)
            if by_root is not None:
                if project_id and by_root["project_id"] != project_id:
                    raise ProjectRegistryError("Project root is already registered with another project_id")
                if project_label:
                    by_root["project_label"] = label
                if proactive_capture:
                    if by_root["status"] != "active":
                        raise ProjectRegistryError("Archived projects cannot enable proactive capture")
                    by_root["proactive_capture"] = True
                return dict(by_root)

            resolved_id = str(project_id or "").strip() or f"proj_{secrets.token_hex(12)}"
            by_id = next((item for item in projects if item["project_id"] == resolved_id), None)
            if by_id is not None and by_id["root"] != normalized_root:
                raise ProjectRegistryError("project_id is already registered for another root")
            record = {
                "project_id": resolved_id,
                "project_label": label,
                "root": normalized_root,
                "status": status,
                "proactive_capture": bool(proactive_capture),
                "created_at": _utc_now(),
                "updated_at": _utc_now(),
            }
            projects.append(record)
            return dict(record)

        return self._mutate(mutate)

    def relocate(self, project_id: str, project_root: Union[str, Path]) -> Dict:
        """Update a registered root while preserving its project_id."""
        normalized_root = normalize_registry_root(project_root)

        def mutate(data):
            projects = data["projects"]
            record = next((item for item in projects if item["project_id"] == project_id), None)
            if record is None:
                raise ProjectRegistryError(f"Unknown project_id: {project_id}")
            conflict = next((item for item in projects if item["root"] == normalized_root), None)
            if conflict is not None and conflict["project_id"] != project_id:
                raise ProjectRegistryError("Project root is already registered to another project_id")
            record["root"] = normalized_root
            record["updated_at"] = _utc_now()
            return dict(record)

        return self._mutate(mutate)

    def rename(self, project_id: str, project_label: str) -> Dict:
        """Change the human label without changing the opaque identity."""
        label = str(project_label or "").strip()
        if not label:
            raise ProjectRegistryError("project_label must not be empty")

        def mutate(data):
            record = next((item for item in data["projects"] if item["project_id"] == project_id), None)
            if record is None:
                raise ProjectRegistryError(f"Unknown project_id: {project_id}")
            record["project_label"] = label
            record["updated_at"] = _utc_now()
            return dict(record)

        return self._mutate(mutate)

    def set_status(self, project_id: str, status: str) -> Dict:
        if status not in VALID_STATUSES:
            raise ProjectRegistryError(f"Unsupported project status: {status}")

        def mutate(data):
            record = next((item for item in data["projects"] if item["project_id"] == project_id), None)
            if record is None:
                raise ProjectRegistryError(f"Unknown project_id: {project_id}")
            record["status"] = status
            if status == "archived":
                record["proactive_capture"] = False
            record["updated_at"] = _utc_now()
            return dict(record)

        return self._mutate(mutate)

    def set_proactive_capture(self, project_id: str, enabled: bool) -> Dict:
        def mutate(data):
            record = next((item for item in data["projects"] if item["project_id"] == project_id), None)
            if record is None:
                raise ProjectRegistryError(f"Unknown project_id: {project_id}")
            if enabled and record["status"] != "active":
                raise ProjectRegistryError("Archived projects cannot enable proactive capture")
            record["proactive_capture"] = bool(enabled)
            record["updated_at"] = _utc_now()
            return dict(record)

        return self._mutate(mutate)

    def migrate_legacy_opt_in_config(self, config_path: Union[str, Path]) -> Dict:
        """Explicitly import legacy config opt-ins into the canonical registry."""
        source = Path(config_path).expanduser()
        if not source.exists():
            return {"status": "missing", "migrated": [], "unchanged": [], "skipped": 0}
        try:
            payload = json.loads(source.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ProjectRegistryError(f"Cannot read legacy opt-in config: {source}") from exc

        configured_roots = payload.get("proactive_opt_in_projects", []) if isinstance(payload, dict) else []
        if not isinstance(configured_roots, list):
            raise ProjectRegistryError("Legacy opt-in config must contain a projects list")

        roots = []
        skipped = 0
        for root in configured_roots:
            if not isinstance(root, str) or not root.strip():
                skipped += 1
                continue
            candidate = Path(root).expanduser()
            if not candidate.is_absolute():
                skipped += 1
                continue
            normalized = normalize_registry_root(candidate)
            if normalized not in roots:
                roots.append(normalized)

        def mutate(data):
            migrated = []
            unchanged = []
            for root in roots:
                record = next((item for item in data["projects"] if item["root"] == root), None)
                if record is None:
                    record = {
                        "project_id": f"proj_{secrets.token_hex(12)}",
                        "project_label": Path(root).name or root,
                        "root": root,
                        "status": "active",
                        "proactive_capture": True,
                        "created_at": _utc_now(),
                        "updated_at": _utc_now(),
                    }
                    data["projects"].append(record)
                    migrated.append(record["project_id"])
                elif record["status"] == "active" and not record["proactive_capture"]:
                    record["proactive_capture"] = True
                    record["updated_at"] = _utc_now()
                    migrated.append(record["project_id"])
                else:
                    unchanged.append(record["project_id"])
            return {
                "status": "migrated",
                "migrated": migrated,
                "unchanged": unchanged,
                "skipped": skipped,
            }

        return self._mutate(mutate)
