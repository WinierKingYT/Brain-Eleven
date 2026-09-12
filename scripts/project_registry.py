#!/usr/bin/env python3
"""Vault-local registry for stable cross-project identities.

The canonical memory records deliberately do not contain filesystem paths.
This small registry is the local-only mapping that lets a project keep the
same opaque identity when its directory is moved or renamed.
"""

import argparse
from copy import deepcopy
import json
import os
import secrets
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Union

try:
    from brain_eleven.infrastructure.locking import file_lock  # noqa: E402
except ModuleNotFoundError as exc:  # pragma: no cover - copied-hook fallback
    if exc.name != "brain_eleven":
        raise
    from memory_store_lock import file_lock  # noqa: E402


REGISTRY_SCHEMA_VERSION = 1
REGISTRY_FILENAME = "project-registry.json"
REGISTRY_BACKUP_FILENAME = "project-registry.backup.json"
BACKUP_SCHEMA_VERSION = 1
VALID_STATUSES = {"active", "archived"}


class ProjectRegistryError(ValueError):
    """Raised when the local project registry is invalid or inconsistent."""


class ProjectRegistryConflict(ProjectRegistryError):
    """Raised when a registry mutation uses an obsolete revision."""

    def __init__(self, expected_revision: int, actual_revision: int):
        self.expected_revision = expected_revision
        self.actual_revision = actual_revision
        super().__init__(
            f"Project registry revision conflict: expected {expected_revision}, "
            f"actual {actual_revision}"
        )


class ProjectRegistryBackupError(ProjectRegistryError):
    """Raised when the fixed registry backup cannot be trusted."""


def registry_path(vault_path: Union[str, Path]) -> Path:
    """Return the ignored, vault-local registry path."""
    return Path(vault_path).expanduser() / ".claude" / REGISTRY_FILENAME


def registry_backup_path(vault_path: Union[str, Path]) -> Path:
    """Return the fixed, vault-local registry backup path."""
    return Path(vault_path).expanduser() / ".claude" / REGISTRY_BACKUP_FILENAME


def normalize_registry_root(project_root: Union[str, Path]) -> str:
    """Normalize a root using the host filesystem's case semantics."""
    root = Path(project_root).expanduser().resolve(strict=False)
    return os.path.normcase(os.path.normpath(str(root)))


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _fsync_parent_directory(path: Path) -> None:
    """Persist the directory entry after replace where the host supports it."""
    if os.name == "nt":
        # Windows flushes the file handle above; directory handles are not
        # consistently openable for fsync across supported Windows versions.
        return
    descriptor = os.open(str(path.parent), os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _atomic_write(path: Path, data: Dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=".project-registry-", suffix=".json", dir=path.parent
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        Path(temporary_name).replace(path)
        _fsync_parent_directory(path)
    finally:
        temporary = Path(temporary_name)
        if temporary.exists():
            temporary.unlink()


def _empty_registry() -> Dict:
    return {
        "schema_version": REGISTRY_SCHEMA_VERSION,
        "revision": 0,
        "updated_at": _utc_now(),
        "projects": [],
    }


class ProjectRegistry:
    """Manage stable project identities without putting roots in memories."""

    def __init__(self, vault_path: Union[str, Path]):
        candidate = Path(vault_path).expanduser()
        self.path = candidate if candidate.name == REGISTRY_FILENAME else registry_path(candidate)
        self.backup_path = self.path.with_name(REGISTRY_BACKUP_FILENAME)

    @staticmethod
    def _normalize(data: Dict) -> Dict:
        if not isinstance(data, dict):
            raise ProjectRegistryError("Project registry must be a JSON object")
        normalized = dict(data)
        # Schema 1 documents written before W-08A did not have a revision.
        normalized.setdefault("revision", 0)
        ProjectRegistry._validate(normalized)
        return normalized

    def load(self) -> Dict:
        """Load and validate the registry; corruption is never treated as empty."""
        if not self.path.exists():
            return _empty_registry()
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ProjectRegistryError(f"Cannot read project registry: {self.path}") from exc
        return self._normalize(data)

    @staticmethod
    def _validate(data: Dict) -> None:
        if not isinstance(data, dict) or data.get("schema_version") != REGISTRY_SCHEMA_VERSION:
            raise ProjectRegistryError("Unsupported project registry schema")
        revision = data.get("revision", 0)
        if isinstance(revision, bool) or not isinstance(revision, int) or revision < 0:
            raise ProjectRegistryError("Project registry revision must be a non-negative integer")
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

    @staticmethod
    def _validate_expected_revision(expected_revision: Optional[int]) -> None:
        if expected_revision is None:
            return
        if isinstance(expected_revision, bool) or not isinstance(expected_revision, int) or expected_revision < 0:
            raise ProjectRegistryError("expected_revision must be a non-negative integer")

    def _write_backup(self, previous: Dict) -> None:
        envelope = {
            "backup_schema_version": BACKUP_SCHEMA_VERSION,
            "captured_at": _utc_now(),
            "source_revision": int(previous["revision"]),
            "registry": deepcopy(previous),
        }
        try:
            _atomic_write(self.backup_path, envelope)
        except (OSError, TypeError, ValueError) as exc:
            raise ProjectRegistryBackupError(
                f"Cannot persist project registry backup: {self.backup_path}"
            ) from exc

    def _persist(self, previous: Dict, current: Dict) -> None:
        if self.path.exists():
            self._write_backup(previous)
        _atomic_write(self.path, current)

    def _mutate(self, callback, expected_revision: Optional[int] = None):
        self._validate_expected_revision(expected_revision)
        with file_lock(self.path):
            data = self.load()
            actual_revision = int(data["revision"])
            if expected_revision is not None and expected_revision != actual_revision:
                raise ProjectRegistryConflict(expected_revision, actual_revision)
            before = deepcopy(data)
            result = callback(data)
            if data == before:
                return result
            data["updated_at"] = _utc_now()
            data["revision"] = actual_revision + 1
            self._validate(data)
            self._persist(before, data)
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
        expected_revision: Optional[int] = None,
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

        return self._mutate(mutate, expected_revision=expected_revision)

    def relocate(
        self,
        project_id: str,
        project_root: Union[str, Path],
        expected_revision: Optional[int] = None,
    ) -> Dict:
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

        return self._mutate(mutate, expected_revision=expected_revision)

    def rename(
        self,
        project_id: str,
        project_label: str,
        expected_revision: Optional[int] = None,
    ) -> Dict:
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

        return self._mutate(mutate, expected_revision=expected_revision)

    def set_status(
        self,
        project_id: str,
        status: str,
        expected_revision: Optional[int] = None,
    ) -> Dict:
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

        return self._mutate(mutate, expected_revision=expected_revision)

    def set_proactive_capture(
        self,
        project_id: str,
        enabled: bool,
        expected_revision: Optional[int] = None,
    ) -> Dict:
        def mutate(data):
            record = next((item for item in data["projects"] if item["project_id"] == project_id), None)
            if record is None:
                raise ProjectRegistryError(f"Unknown project_id: {project_id}")
            if enabled and record["status"] != "active":
                raise ProjectRegistryError("Archived projects cannot enable proactive capture")
            record["proactive_capture"] = bool(enabled)
            record["updated_at"] = _utc_now()
            return dict(record)

        return self._mutate(mutate, expected_revision=expected_revision)

    def migrate_legacy_opt_in_config(
        self,
        config_path: Union[str, Path],
        expected_revision: Optional[int] = None,
    ) -> Dict:
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

        return self._mutate(mutate, expected_revision=expected_revision)

    def rollback(self, *, expected_revision: int) -> Dict:
        """Restore the fixed backup without moving the registry revision backwards."""
        self._validate_expected_revision(expected_revision)
        with file_lock(self.path):
            current = self.load()
            actual_revision = int(current["revision"])
            if expected_revision != actual_revision:
                raise ProjectRegistryConflict(expected_revision, actual_revision)
            if not self.backup_path.is_file():
                raise ProjectRegistryBackupError(
                    f"Project registry backup does not exist: {self.backup_path}"
                )
            try:
                envelope = json.loads(self.backup_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise ProjectRegistryBackupError(
                    f"Cannot read project registry backup: {self.backup_path}"
                ) from exc
            if not isinstance(envelope, dict) or envelope.get("backup_schema_version") != BACKUP_SCHEMA_VERSION:
                raise ProjectRegistryBackupError("Unsupported project registry backup schema")
            backup = envelope.get("registry")
            source_revision = envelope.get("source_revision")
            if not isinstance(source_revision, int) or source_revision < 0 or not isinstance(backup, dict):
                raise ProjectRegistryBackupError("Project registry backup envelope is invalid")
            normalized_backup = self._normalize(backup)
            if source_revision != int(normalized_backup["revision"]):
                raise ProjectRegistryBackupError("Project registry backup revision is inconsistent")
            if current.get("projects") == normalized_backup.get("projects"):
                return {
                    "status": "already_restored",
                    "revision": actual_revision,
                    "source_revision": source_revision,
                }
            restored = deepcopy(normalized_backup)
            restored["revision"] = actual_revision + 1
            restored["updated_at"] = _utc_now()
            self._validate(restored)
            # Keep the verified backup as the rollback source. A later ordinary
            # mutation will rotate it to the then-current registry.
            _atomic_write(self.path, restored)
            return {
                "status": "rolled_back",
                "revision": restored["revision"],
                "source_revision": source_revision,
            }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Manage Brain-Eleven project identities")
    parser.add_argument("--vault", default=".")
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_parser = subparsers.add_parser("list")
    list_parser.set_defaults(command_handler=lambda registry, args: registry.list_projects())

    register = subparsers.add_parser("register")
    register.add_argument("root")
    register.add_argument("--label", default=None)
    register.add_argument(
        "--proactive",
        action="store_true",
        help="Enable proactive capture for this active project",
    )
    register.set_defaults(
        command_handler=lambda registry, args: registry.register(
            args.root,
            args.label,
            proactive_capture=args.proactive,
        )
    )

    relocate = subparsers.add_parser("relocate")
    relocate.add_argument("project_id")
    relocate.add_argument("root")
    relocate.set_defaults(command_handler=lambda registry, args: registry.relocate(args.project_id, args.root))

    rename = subparsers.add_parser("rename")
    rename.add_argument("project_id")
    rename.add_argument("label")
    rename.set_defaults(command_handler=lambda registry, args: registry.rename(args.project_id, args.label))

    status = subparsers.add_parser("status")
    status.add_argument("project_id")
    status.add_argument("value", choices=("active", "archived"))
    status.set_defaults(command_handler=lambda registry, args: registry.set_status(args.project_id, args.value))

    proactive = subparsers.add_parser("proactive")
    proactive.add_argument("project_id")
    proactive.add_argument("value", choices=("on", "off"))
    proactive.set_defaults(
        command_handler=lambda registry, args: registry.set_proactive_capture(
            args.project_id, args.value == "on"
        )
    )

    migrate_legacy = subparsers.add_parser("migrate-legacy-opt-in")
    migrate_legacy.add_argument("--config", required=True)
    migrate_legacy.set_defaults(
        command_handler=lambda registry, args: registry.migrate_legacy_opt_in_config(args.config)
    )

    rollback = subparsers.add_parser("rollback")
    rollback.add_argument("--expected-revision", type=int, required=True)
    rollback.set_defaults(
        command_handler=lambda registry, args: registry.rollback(
            expected_revision=args.expected_revision
        )
    )

    args = parser.parse_args(argv)
    result = args.command_handler(ProjectRegistry(Path(args.vault)), args)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
