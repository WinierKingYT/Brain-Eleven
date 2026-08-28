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
        """List all active memories (by immutable ID)"""
        active = [m for m in self.memories if m.get("status", "active") == "active"]

        print(f"\n📋 Active Memories ({len(active)} total)\n")
        for i, m in enumerate(active, 1):
            mem_id = m.get("memory_id", m.get("id", "unknown"))
            print(f"{i}. [{m['type'].upper()}] {mem_id}")
            print(f"   {m['content'][:80]}...")
            print(f"   Score: {m['quality_score']:.2f}, Confidence: {m['confidence']:.2f}\n")

        return active

    def resolve_memory(
        self,
        memory_id: str,
        resolved_by: str,
        reason: str = ""
    ) -> bool:
        """Mark a memory as resolved (by immutable ULID)"""

        memory = None
        for m in self.memories:
            # Try new memory_id field first, fallback to legacy id
            if m.get("memory_id") == memory_id or str(m.get("id")) == memory_id:
                memory = m
                break

        if not memory:
            print(f"❌ Memory {memory_id} not found")
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
        memory_id: str,
        superseded_by: str,
        reason: str = ""
    ) -> bool:
        """Mark a memory as superseded and link to new memory (by immutable ULID)"""

        memory = None
        for m in self.memories:
            # Try new memory_id field first, fallback to legacy id
            if m.get("memory_id") == memory_id or str(m.get("id")) == memory_id:
                memory = m
                break

        if not memory:
            print(f"❌ Memory {memory_id} not found")
            return False

        # Update status
        memory["status"] = "superseded"
        memory["resolved_at"] = datetime.now().isoformat()
        memory["superseded_by"] = superseded_by  # ULID of new memory

        if reason:
            memory["supersession_note"] = reason

        print(f"✅ Marked as superseded:")
        print(f"   Memory: {memory['content'][:60]}...")
        print(f"   Superseded by: {superseded_by}")
        if reason:
            print(f"   Reason: {reason}")

        return True

    def trace_provenance(self, memory_id: str) -> List[Dict]:
        """Trace full lifecycle chain (supersessions and resolutions)"""

        memory = None
        for m in self.memories:
            if m.get("memory_id") == memory_id or str(m.get("id")) == memory_id:
                memory = m
                break

        if not memory:
            print(f"❌ Memory {memory_id} not found")
            return []

        chain = [memory]
        current = memory

        # Follow supersession chain forward
        while current.get("superseded_by"):
            next_id = current["superseded_by"]
            next_mem = None
            for m in self.memories:
                if m.get("memory_id") == next_id:
                    next_mem = m
                    break

            if next_mem:
                chain.append(next_mem)
                current = next_mem
            else:
                break

        # Print chain
        print(f"\n🔗 Provenance chain for {memory_id}:")
        for i, mem in enumerate(chain):
            status = mem.get("status", "active")
            content = mem["content"][:50]
            mid = mem.get("memory_id", "?")
            print(f"  {i+1}. [{status.upper()}] {mid}")
            print(f"     {content}...")
            if mem.get("resolved_at"):
                print(f"     Resolved: {mem['resolved_at']}")
            if mem.get("superseded_by"):
                print(f"     Superseded by: {mem['superseded_by']}")

        return chain

    def save(self):
        """Save updated memories with atomic persistence"""

        import tempfile
        import shutil

        # Read current data
        with open(self.validated_json, 'r', encoding='utf-8') as f:
            data = json.load(f)

        data["validated_memory"] = self.memories
        data["last_updated"] = datetime.now().isoformat()

        # Atomic write: temp → validate → rename
        try:
            temp_fd, temp_path = tempfile.mkstemp(
                dir=self.validated_json.parent,
                prefix='.tmp_',
                suffix='.json'
            )

            with open(temp_fd, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

            # Validate
            with open(temp_path, 'r', encoding='utf-8') as f:
                validate_data = json.load(f)

            if "validated_memory" not in validate_data:
                raise ValueError("Invalid structure")

            # Atomic rename
            if self.validated_json.exists():
                backup = self.validated_json.with_suffix('.backup.json')
                shutil.copy2(self.validated_json, backup)

            shutil.move(temp_path, self.validated_json)
            print(f"✅ Atomically saved to {self.validated_json}")

        except Exception as e:
            print(f"❌ Atomic save failed: {e}")
            try:
                if Path(temp_path).exists():
                    Path(temp_path).unlink()
            except:
                pass


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
            print("❌ Usage: resolve <memory_id> <commit_hash> [reason]")
            print("   Example: resolve 01M155WB9AKKTCZWTFRDDZR4W7 69b6437 'reason'")
            sys.exit(1)

        memory_id = sys.argv[2]  # Now accepts ULID string or legacy integer
        resolved_by = sys.argv[3]
        reason = " ".join(sys.argv[4:]) if len(sys.argv) > 4 else ""

        if manager.resolve_memory(memory_id, resolved_by, reason):
            manager.save()

    elif command == "supersede":
        if len(sys.argv) < 4:
            print("❌ Usage: supersede <memory_id> <new_source> [reason]")
            print("   Example: supersede 01M155WB9AKKTCZWTFRDDZR4W7 'mem_new_id' 'reason'")
            sys.exit(1)

        memory_id = sys.argv[2]  # Now accepts ULID string or legacy integer
        superseded_by = sys.argv[3]
        reason = " ".join(sys.argv[4:]) if len(sys.argv) > 4 else ""

        if manager.supersede_memory(memory_id, superseded_by, reason):
            manager.save()

    else:
        print(f"❌ Unknown command: {command}")
        sys.exit(1)
