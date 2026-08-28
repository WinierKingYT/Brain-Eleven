#!/usr/bin/env python3
"""
Brain-Eleven Memory Lifecycle Manager
Mark memories as resolved, superseded, or archived

Pipeline:
  Memory (status: active)
    ↓
  User marks: resolved / superseded
    ↓
  Update validated-memory.json with status + timestamp + reference
    ↓
  Retriever skips these on next search
"""

import json
import sys
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional


class MemoryLifecycleManager:
    """Manage memory status transitions"""

    def __init__(self, vault_path: str):
        self.vault_path = Path(vault_path)
        self.validated_json = self.vault_path / ".claude/validated-memory.json"
        self.memories = []
        self._load_memories()

    def _load_memories(self):
        """Load validated memories"""
        if not self.validated_json.exists():
            print("⚠️  validated-memory.json not found")
            return

        with open(self.validated_json, 'r', encoding='utf-8') as f:
            data = json.load(f)

        self.memories = data.get("validated_memory", [])

    def list_active(self) -> List[Dict]:
        """List all active memories"""
        active = [m for m in self.memories if m.get("status", "active") == "active"]

        print(f"\n📋 Active Memories ({len(active)} total)\n")
        for i, m in enumerate(active, 1):
            print(f"{i}. [{m['type'].upper()}] ID {m['id']}")
            print(f"   {m['content'][:80]}...")
            print(f"   Score: {m['quality_score']:.2f}, Confidence: {m['confidence']:.2f}\n")

        return active

    def resolve_memory(
        self,
        memory_id: int,
        resolved_by: str,
        reason: str = ""
    ) -> bool:
        """Mark a memory as resolved"""

        memory = None
        for m in self.memories:
            if m["id"] == memory_id:
                memory = m
                break

        if not memory:
            print(f"❌ Memory ID {memory_id} not found")
            return False

        # Update status
        memory["status"] = "resolved"
        memory["resolved_at"] = datetime.now().isoformat()
        memory["resolved_by"] = resolved_by

        if reason:
            memory["resolution_note"] = reason

        print(f"✅ Marked as resolved:")
        print(f"   Memory: {memory['content'][:60]}...")
        print(f"   Status: {memory['status']}")
        print(f"   Resolved by: {resolved_by}")

        return True

    def supersede_memory(
        self,
        memory_id: int,
        superseded_by: str,
        reason: str = ""
    ) -> bool:
        """Mark a memory as superseded by newer information"""

        memory = None
        for m in self.memories:
            if m["id"] == memory_id:
                memory = m
                break

        if not memory:
            print(f"❌ Memory ID {memory_id} not found")
            return False

        # Update status
        memory["status"] = "superseded"
        memory["resolved_at"] = datetime.now().isoformat()
        memory["superseded_by"] = superseded_by

        if reason:
            memory["supersession_note"] = reason

        print(f"✅ Marked as superseded:")
        print(f"   Memory: {memory['content'][:60]}...")
        print(f"   Superseded by: {superseded_by}")

        return True

    def save(self):
        """Save updated memories back to JSON"""
        with open(self.validated_json, 'r', encoding='utf-8') as f:
            data = json.load(f)

        data["validated_memory"] = self.memories
        data["last_updated"] = datetime.now().isoformat()

        with open(self.validated_json, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        print(f"\n💾 Saved to {self.validated_json}")


# ============================================================================
# CLI
# ============================================================================

if __name__ == "__main__":
    vault_path = Path.home() / "Documents/Brain-Eleven"
    manager = MemoryLifecycleManager(str(vault_path))

    if len(sys.argv) < 2:
        # List active memories
        manager.list_active()
        print("\n📖 Usage:")
        print("   memory-lifecycle.py list")
        print("   memory-lifecycle.py resolve <id> <commit_hash> [reason]")
        print("   memory-lifecycle.py supersede <id> <new_source> [reason]")
        print("")
        print("Example:")
        print('   memory-lifecycle.py resolve 10 "69b6437" "Retrieval engine complete"')
        sys.exit(0)

    command = sys.argv[1]

    if command == "list":
        manager.list_active()

    elif command == "resolve":
        if len(sys.argv) < 4:
            print("❌ Usage: resolve <id> <commit_hash> [reason]")
            sys.exit(1)

        memory_id = int(sys.argv[2])
        resolved_by = sys.argv[3]
        reason = " ".join(sys.argv[4:]) if len(sys.argv) > 4 else ""

        if manager.resolve_memory(memory_id, resolved_by, reason):
            manager.save()

    elif command == "supersede":
        if len(sys.argv) < 4:
            print("❌ Usage: supersede <id> <new_source> [reason]")
            sys.exit(1)

        memory_id = int(sys.argv[2])
        superseded_by = sys.argv[3]
        reason = " ".join(sys.argv[4:]) if len(sys.argv) > 4 else ""

        if manager.supersede_memory(memory_id, superseded_by, reason):
            manager.save()

    else:
        print(f"❌ Unknown command: {command}")
        sys.exit(1)
