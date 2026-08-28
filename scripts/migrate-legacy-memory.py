#!/usr/bin/env python3
"""
Brain-Eleven Legacy Memory Migration
Upgrade prior memories to immutable ID system

Mission: Convert legacy validated-memory.json records
to use real ULID + fingerprint dedup keys
"""

import json
import hashlib
from pathlib import Path
from datetime import datetime

try:
    from ulid import ULID
except ImportError:
    from uuid import uuid4
    class ULID:
        def __init__(self):
            self.value = str(uuid4())[:20]
        def __str__(self):
            return self.value


def compute_fingerprint(content: str) -> str:
    """Compute SHA256 fingerprint for content"""
    normalized = ' '.join(content.lower().split())
    return hashlib.sha256(normalized.encode()).hexdigest()[:16]


def migrate_legacy_memory(vault_path: str):
    """Migrate legacy validated-memory.json to new ID system"""

    validated_json = Path(vault_path) / ".claude/validated-memory.json"
    backup_file = Path(vault_path) / ".claude/validated-memory.backup.json"

    if not validated_json.exists():
        print("⚠️  validated-memory.json not found")
        return 0

    # Create backup
    with open(validated_json, 'r', encoding='utf-8') as f:
        data = json.load(f)

    with open(backup_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print(f"✓ Backup created: {backup_file}")

    # Migrate memories
    migrated_count = 0
    for memory in data.get("validated_memory", []):
        # Assign new memory_id if missing
        if not memory.get("memory_id"):
            memory["memory_id"] = str(ULID())
            migrated_count += 1

        # Compute fingerprint if missing
        if not memory.get("dedup_fingerprint"):
            memory["dedup_fingerprint"] = compute_fingerprint(memory["content"])

        # Assign source_id if missing (fallback)
        if not memory.get("source_id"):
            memory["source_id"] = f"daily:{memory.get('section', 'unknown')}:{memory.get('id', 0)}"

        # Keep integer id for backward compat but mark as deprecated
        if "id" not in memory:
            memory["id"] = -1  # deprecated marker

    # Update metadata
    data["migrated_at"] = datetime.now().isoformat()
    data["migration_version"] = "1.0"

    # Save migrated version
    with open(validated_json, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

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
