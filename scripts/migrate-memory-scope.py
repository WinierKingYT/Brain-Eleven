#!/usr/bin/env python3
"""Safely migrate legacy memory records to the explicit scope-aware schema."""

import argparse
import json
import shutil
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Tuple, Union

from memory_scope import GLOBAL_SCOPE, PROJECT_SCOPE, infer_memory_scope, scoped_fingerprint
from memory_store import MemoryStore, MemoryStoreCorrupt, no_change


MIGRATION_NAME = "scope-v2"


class MemoryScopeMigrationError(RuntimeError):
    """Raised when a migration input cannot be changed without inventing meaning."""


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")


def _create_exact_backup(memory_file: Path) -> Path:
    """Copy the on-disk pre-migration document before altering it."""
    backup = memory_file.with_name(
        f"{memory_file.name}.pre-{MIGRATION_NAME}-{_utc_stamp()}.bak"
    )
    shutil.copy2(memory_file, backup)
    return backup


def _schema_upgrade_required(memory_file: Path) -> bool:
    """Check the physical envelope because ``MemoryStore.load`` normalizes v1 in memory."""
    raw_document = json.loads(memory_file.read_text(encoding="utf-8"))
    return raw_document.get("schema_version", 1) != 2


def _review_reason(record: Dict) -> str:
    """Reject ambiguous legacy metadata instead of inferring a false identity."""
    raw_scope = record.get("scope")
    project = str(record.get("project_label") or record.get("project") or "").strip()
    project_id = str(record.get("project_id") or "").strip()

    if raw_scope not in (None, "", GLOBAL_SCOPE, PROJECT_SCOPE):
        return "unsupported_scope"
    if raw_scope == PROJECT_SCOPE and not (project or project_id):
        return "project_scope_without_identity"
    if raw_scope == GLOBAL_SCOPE and (project or project_id):
        return "global_scope_with_project_metadata"
    return ""


def _migrate_document(data: Dict) -> Tuple[Dict, int, List[Dict]]:
    """Create a scope-v2 candidate without changing the source document."""
    changed = 0
    migrated: Dict[str, List[Dict]] = {}
    needs_review: List[Dict] = []

    for bucket in ("validated_memory", "rejected_memory"):
        records = data.get(bucket, [])
        migrated[bucket] = []
        for index, record in enumerate(records):
            if not isinstance(record, dict):
                raise MemoryScopeMigrationError(
                    f"{bucket}[{index}] is not a memory object"
                )

            reason = _review_reason(record)
            if reason:
                needs_review.append({
                    "bucket": bucket,
                    "index": index,
                    "memory_id": record.get("memory_id"),
                    "reason": reason,
                })
                migrated[bucket].append(dict(record))
                continue

            updated = dict(record)
            scope, project, project_id = infer_memory_scope(record)
            fingerprint = scoped_fingerprint(
                record.get("content", ""), scope, project_id, record.get("type", "")
            )
            updated.update({
                "scope": scope,
                "project": project,
                "project_label": project,
                "project_id": project_id,
                "dedup_fingerprint": fingerprint,
            })
            if any(updated.get(key) != record.get(key) for key in (
                "scope", "project", "project_label", "project_id", "dedup_fingerprint"
            )):
                changed += 1
            migrated[bucket].append(updated)

    output = dict(data)
    output.update(migrated)
    return output, changed, needs_review


def _result(
    status: str,
    changed: int,
    memory_file: Path,
    backup: Path = None,
    needs_review: List[Dict] = None,
    source_revision: int = None,
    revision: int = None,
    schema_upgraded: bool = False,
) -> Dict:
    return {
        "status": status,
        "migration": MIGRATION_NAME,
        "changed": changed,
        "backup": str(backup) if backup else None,
        "memory_file": str(memory_file),
        "needs_review": needs_review or [],
        "source_revision": source_revision,
        "revision": revision,
        "schema_upgraded": schema_upgraded,
    }


def migrate(vault_path: Union[str, Path], dry_run: bool = False) -> Dict:
    """Migrate the canonical store with pre-flight, exact backup and safe reruns."""
    vault = Path(vault_path)
    memory_file = vault / ".claude" / "validated-memory.json"
    if not memory_file.exists():
        return _result("no_store", 0, memory_file)

    store = MemoryStore(vault)
    if dry_run:
        document = store.load()
        _output, changed, needs_review = _migrate_document(document)
        status = "needs_review" if needs_review else "dry_run"
        return _result(
            status,
            changed,
            memory_file,
            needs_review=needs_review,
            source_revision=int(document["revision"]),
            revision=int(document["revision"]),
            schema_upgraded=_schema_upgrade_required(memory_file),
        )

    def mutate(data: Dict):
        output, changed, needs_review = _migrate_document(data)
        source_revision = int(data["revision"])
        schema_upgrade = _schema_upgrade_required(memory_file)
        if needs_review:
            return no_change(_result(
                "needs_review",
                changed,
                memory_file,
                needs_review=needs_review,
                source_revision=source_revision,
                revision=source_revision,
                schema_upgraded=schema_upgrade,
            ))
        if not changed and not schema_upgrade:
            return no_change(_result(
                "unchanged",
                0,
                memory_file,
                source_revision=source_revision,
                revision=source_revision,
            ))

        backup = _create_exact_backup(memory_file)
        data.clear()
        data.update(output)
        return _result(
            "migrated",
            changed,
            memory_file,
            backup=backup,
            source_revision=source_revision,
            schema_upgraded=schema_upgrade,
        )

    result, persisted = store.transact(mutate)
    result["revision"] = int(persisted["revision"])
    return result


def rollback(vault_path: Union[str, Path], backup_path: Union[str, Path]) -> Dict:
    """Restore a validated pre-migration backup through the canonical store."""
    vault = Path(vault_path)
    backup = Path(backup_path).expanduser()
    if not backup.is_file():
        raise MemoryScopeMigrationError(f"Migration backup does not exist: {backup}")
    try:
        backup_document = json.loads(backup.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise MemoryScopeMigrationError(f"Cannot read migration backup: {backup}") from exc

    try:
        normalized_backup = MemoryStore._normalize(backup_document)
    except MemoryStoreCorrupt as exc:
        raise MemoryScopeMigrationError(f"Invalid migration backup: {backup}") from exc

    store = MemoryStore(vault)
    persisted = store.replace(deepcopy(normalized_backup))
    return {
        "status": "rolled_back",
        "migration": MIGRATION_NAME,
        "backup": str(backup),
        "source_revision": int(normalized_backup["revision"]),
        "revision": int(persisted["revision"]),
        "memory_file": str(store.path),
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Migrate Brain-Eleven memories to explicit scope metadata"
    )
    parser.add_argument("--vault", default=".")
    operation = parser.add_mutually_exclusive_group()
    operation.add_argument("--dry-run", action="store_true")
    operation.add_argument("--rollback", metavar="BACKUP")
    args = parser.parse_args(argv)

    result = (
        rollback(args.vault, args.rollback)
        if args.rollback
        else migrate(args.vault, dry_run=args.dry_run)
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
