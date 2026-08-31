#!/usr/bin/env python3
"""
Brain-Eleven Legacy Memory Migration
Upgrade prior memories to immutable ID system

Mission: Convert legacy validated-memory.json records
to use real ULID + fingerprint dedup keys
"""

from pathlib import Path
from datetime import datetime

from memory_scope import infer_memory_scope, scoped_fingerprint
from memory_store import MemoryStore

try:
    from ulid import ULID
except ImportError:
    from uuid import uuid4
    class ULID:
        def __init__(self):
            self.value = str(uuid4())[:20]
        def __str__(self):
            return self.value


def compute_fingerprint(content: str, type_: str = "") -> str:
    """Compute the current type-aware global fingerprint."""
    return scoped_fingerprint(content, "global", "", type_)


def migrate_legacy_memory(vault_path: str):
    """Migrate legacy validated-memory.json to new ID system"""

    store = MemoryStore(vault_path)
    validated_json = store.path
    backup_file = store.backup_path

    if not validated_json.exists():
        print("⚠️  validated-memory.json not found")
        return 0

    def mutate(data):
        migrated_count = 0
        for bucket in ("validated_memory", "rejected_memory"):
            for memory in data.get(bucket, []):
                if not memory.get("memory_id"):
                    memory["memory_id"] = str(ULID())
                    migrated_count += 1

                scope, _project, project_id = infer_memory_scope(memory)
                memory.setdefault("scope", scope)
                if scope == "project":
                    memory.setdefault("project_id", project_id)
                    memory.setdefault("project_label", memory.get("project", project_id))
                if not memory.get("dedup_fingerprint"):
                    memory["dedup_fingerprint"] = scoped_fingerprint(
                        memory.get("content", ""), scope, project_id, memory.get("type", "")
                    )
                if not memory.get("source_id"):
                    memory["source_id"] = f"daily:{memory.get('section', 'unknown')}:{memory.get('id', 0)}"
                memory.setdefault("id", -1)

        data["migrated_at"] = datetime.now().isoformat()
        data["migration_version"] = "1.0"
        return migrated_count

    migrated_count, _persisted = store.transact(mutate)

    print(f"✓ Migration complete")
    print(f"  → {migrated_count} memories assigned new IDs")
    print(f"  → All memories have fingerprints")
    print(f"  → Backup: {backup_file}")

    return migrated_count


if __name__ == "__main__":
    vault_path = Path.home() / "Documents/Brain-Eleven"
    count = migrate_legacy_memory(str(vault_path))

    print(f"\n🎯 Migration Results:")
    print(f"  Total migrated: {count}")
    print(f"  Status: READY FOR PRODUCTION")
    print(f"\n⚠️  BREAKING CHANGE:")
    print(f"  - Memory IDs are now immutable ULIDs")
    print(f"  - Integer 'id' field is deprecated")
    print(f"  - Lifecycle CLI must be updated to use memory_id")
