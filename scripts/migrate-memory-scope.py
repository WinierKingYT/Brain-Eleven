#!/usr/bin/env python3
"""Migrate legacy memory records to the explicit scope-aware schema."""

import argparse
import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Union

from memory_scope import infer_memory_scope, scoped_fingerprint
from memory_store import MemoryStore, no_change


def migrate(vault_path: Union[str, Path], dry_run: bool = False) -> Dict:
    """Migrate the canonical store without changing memory identities."""
    vault = Path(vault_path)
    memory_file = vault / ".claude" / "validated-memory.json"
    if not memory_file.exists():
        return {"status": "no_store", "changed": 0, "backup": None}

    store = MemoryStore(vault)

    def migrate_document(data: Dict):
        changed = 0
        migrated: Dict[str, List[Dict]] = {}
        for bucket in ("validated_memory", "rejected_memory"):
            records = data.get(bucket, [])
            migrated[bucket] = []
            for record in records:
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
        return output, changed

    backup = None
    if dry_run:
        _output, changed = migrate_document(store.load())
    else:
        def mutate(data):
            nonlocal backup
            output, changed = migrate_document(data)
            if not changed:
                return no_change((0, None))
            suffix = datetime.now().strftime("%Y%m%d%H%M%S")
            backup_path = memory_file.with_name(f"{memory_file.name}.pre-scope-{suffix}.bak")
            shutil.copy2(memory_file, backup_path)
            data.clear()
            data.update(output)
            backup = str(backup_path)
            return changed, backup

        (changed, _backup), _persisted = store.transact(mutate)

    return {
        "status": "dry_run" if dry_run else ("migrated" if changed else "unchanged"),
        "changed": changed,
        "backup": backup,
        "memory_file": str(memory_file),
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Migrate Brain-Eleven memories to explicit scope metadata")
    parser.add_argument("--vault", default=".")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    print(json.dumps(migrate(args.vault, dry_run=args.dry_run), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
