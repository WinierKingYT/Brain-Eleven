#!/usr/bin/env python3
"""Create and restore verified backups of Brain-Eleven canonical memory.

The canonical store is the authority.  Knowledge graphs, context bootstraps,
compiled candidates, and caches are deliberately excluded: a restore must
prove that those projections can be rebuilt from canonical data.
"""

import argparse
import hashlib
import importlib.util
import json
import os
import shutil
import sys
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Dict, Iterable, List, Optional, Tuple, Union

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from brain_eleven.extraction import EntityExtractor
from memory_scope import (
    GLOBAL_SCOPE,
    PROJECT_SCOPE,
    infer_memory_scope,
    scoped_fingerprint,
)
from memory_store import CANONICAL_SCHEMA_VERSION, MemoryStore, MemoryStoreCorrupt
from brain_eleven.projects.registry import (
    REGISTRY_FILENAME,
    ProjectRegistry,
    ProjectRegistryError,
    registry_path,
)
from state_store import StateSchemaError, StateStore, validate_state_document


BACKUP_SCHEMA_VERSION = 2
SUPPORTED_BACKUP_SCHEMA_VERSIONS = frozenset({1, BACKUP_SCHEMA_VERSION})
BACKUP_FORMAT = "brain-eleven-memory-backup"
MANIFEST_PATH = "manifest.json"
CANONICAL_ARCHIVE_PATH = "canonical/validated-memory.json"
REGISTRY_ARCHIVE_PATH = "registry/project-registry.json"
SETTINGS_ARCHIVE_PATH = "config/settings.json"
STATE_ARCHIVE_PATH = "state/project-state.json"

RESTORE_PATHS = {
    CANONICAL_ARCHIVE_PATH: Path(".claude") / "validated-memory.json",
    REGISTRY_ARCHIVE_PATH: Path(".claude") / REGISTRY_FILENAME,
    SETTINGS_ARCHIVE_PATH: Path(".claude") / "settings.json",
    STATE_ARCHIVE_PATH: Path(".claude") / "project-state.json",
}


class MemoryBackupError(RuntimeError):
    """Raised when a backup cannot be trusted, created, or safely restored."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _json_object(payload: bytes, label: str) -> Dict:
    try:
        value = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
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
    if document.get("schema_version") != CANONICAL_SCHEMA_VERSION:
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
                raise MemoryBackupError(f"Canonical memory has duplicate memory_id: {memory_id}")
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
        raise MemoryBackupError(f"Project state is invalid: {exc}") from exc


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
            raise MemoryBackupError(
                "Project registry is missing canonical project identities: " + ", ".join(missing)
            )

    if project_state is not None:
        if registry is None:
            raise MemoryBackupError("Canonical project state requires a project registry backup")
        registered_ids = {project["project_id"] for project in registry["projects"]}
        state_project_ids = set(project_state["projects"])
        missing_state_projects = sorted(state_project_ids - registered_ids)
        if missing_state_projects:
            raise MemoryBackupError(
                "Project registry is missing canonical state identities: "
                + ", ".join(missing_state_projects)
            )

    return {
        "canonical": canonical,
        "memory_ids": memory_ids,
        "project_ids": project_ids,
        "registry": registry,
        "state": project_state,
    }


def _read_source_payloads(vault_path: Union[str, Path]) -> Dict[str, bytes]:
    vault = Path(vault_path).expanduser()
    canonical_path = vault / RESTORE_PATHS[CANONICAL_ARCHIVE_PATH]
    if not canonical_path.is_file():
        raise MemoryBackupError(f"Canonical memory does not exist: {canonical_path}")

    payloads = {CANONICAL_ARCHIVE_PATH: canonical_path.read_bytes()}
    registry_file = registry_path(vault)
    if registry_file.exists():
        payloads[REGISTRY_ARCHIVE_PATH] = registry_file.read_bytes()
    settings_file = vault / RESTORE_PATHS[SETTINGS_ARCHIVE_PATH]
    if settings_file.exists():
        payloads[SETTINGS_ARCHIVE_PATH] = settings_file.read_bytes()
    state_file = vault / RESTORE_PATHS[STATE_ARCHIVE_PATH]
    if state_file.exists():
        payloads[STATE_ARCHIVE_PATH] = state_file.read_bytes()
    _validate_snapshot(payloads)
    return payloads


def _manifest_for(payloads: Dict[str, bytes], snapshot: Dict) -> Dict:
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
            "canonical_schema_version": CANONICAL_SCHEMA_VERSION,
            "scope_metadata": "embedded_in_canonical_records",
        },
        "files": files,
    }


def _atomic_create_archive(output_path: Path, manifest: Dict, payloads: Dict[str, bytes]) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=".memory-backup-", suffix=".zip", dir=output_path.parent
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr(MANIFEST_PATH, json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
            for archive_path, payload in sorted(payloads.items()):
                archive.writestr(archive_path, payload)
        temporary.replace(output_path)
    except (OSError, zipfile.BadZipFile) as exc:
        raise MemoryBackupError(f"Cannot create backup archive: {output_path}") from exc
    finally:
        if temporary.exists():
            temporary.unlink()


def _expected_archive_path(path: str) -> bool:
    pure = PurePosixPath(path)
    return (
        path in RESTORE_PATHS
        and not pure.is_absolute()
        and ".." not in pure.parts
        and "\\" not in path
    )


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
    return manifest, payloads, snapshot


def create_backup(vault_path: Union[str, Path], archive_path: Union[str, Path]) -> Dict:
    """Write a verified backup of canonical authorities, excluding projections."""
    payloads = _read_source_payloads(vault_path)
    snapshot = _validate_snapshot(payloads)
    output = Path(archive_path).expanduser()
    if output.exists():
        raise MemoryBackupError(f"Refusing to overwrite an existing backup: {output}")
    _atomic_create_archive(output, _manifest_for(payloads, snapshot), payloads)
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
