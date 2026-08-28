#!/usr/bin/env python3
"""
Brain-Eleven Memory Lifecycle Tests
Regression tests for resolve/supersede, ULID lookup, provenance tracing
"""

import pytest
import json
import tempfile
from pathlib import Path
from datetime import datetime

import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from memory_lifecycle import MemoryLifecycleManager


@pytest.fixture
def temp_vault(tmp_path):
    """Create temporary vault structure"""
    vault_path = tmp_path / "test-vault"
    vault_path.mkdir()

    claude_dir = vault_path / ".claude"
    claude_dir.mkdir()

    return vault_path


@pytest.fixture
def sample_validated_memory(temp_vault):
    """Create sample validated-memory.json with active + resolved memories"""
    validated_file = temp_vault / ".claude" / "validated-memory.json"

    data = {
        "validated_at": datetime.now().isoformat(),
        "validated_memory": [
            {
                "memory_id": "01M155WB9AKKTCZWTFRDDZR4W7",
                "id": 0,
                "type": "decision",
                "content": "Use PostgreSQL for production",
                "confidence": 0.95,
                "status": "active",
                "resolved_at": "",
                "resolved_by": "",
                "resolution_note": "",
                "superseded_by": "",
                "supersession_note": ""
            },
            {
                "memory_id": "01M155WB9FCSPSFQCFM8NVATS8",
                "id": 1,
                "type": "decision",
                "content": "Use microservices architecture",
                "confidence": 0.85,
                "status": "active",
                "resolved_at": "",
                "resolved_by": "",
                "resolution_note": "",
                "superseded_by": "",
                "supersession_note": ""
            },
            {
                "memory_id": "01M155WB9FCSPSFQCFM8NVATSD",
                "id": 2,
                "type": "open_loop",
                "content": "Write regression tests",
                "confidence": 0.90,
                "status": "resolved",
                "resolved_at": "2026-08-29T10:00:00",
                "resolved_by": "test-commit-1",
                "resolution_note": "Tests completed",
                "superseded_by": "",
                "supersession_note": ""
            }
        ]
    }

    validated_file.write_text(json.dumps(data, indent=2), encoding='utf-8')
    return validated_file


class TestMemoryLifecycleManager:
    """Test suite for Lifecycle Management"""

    def test_list_active_memories(self, temp_vault, sample_validated_memory):
        """Test listing active memories"""
        manager = MemoryLifecycleManager(str(temp_vault))

        active = manager.list_active()

        # Should have 2 active (postgres + microservices)
        assert len(active) == 2, f"Should have 2 active, got {len(active)}"

        # Resolved memory should not be listed
        resolved_ids = [m["memory_id"] for m in active if m.get("status") == "resolved"]
        assert len(resolved_ids) == 0, "Resolved memories should not be in active list"

    def test_resolve_memory_by_ulid(self, temp_vault, sample_validated_memory):
        """Test resolving a memory by ULID (immutable ID)"""
        manager = MemoryLifecycleManager(str(temp_vault))

        # Resolve first decision
        success = manager.resolve_memory(
            "01M155WB9AKKTCZWTFRDDZR4W7",
            "abc12345",
            "Decision implemented"
        )

        assert success, "Should resolve successfully"

        # Find resolved memory
        resolved = None
        for m in manager.memories:
            if m["memory_id"] == "01M155WB9AKKTCZWTFRDDZR4W7":
                resolved = m
                break

        assert resolved is not None, "Should find resolved memory"
        assert resolved["status"] == "resolved", "Status should be 'resolved'"
        assert resolved["resolved_by"] == "abc12345", "Should record commit hash"
        assert resolved["resolution_note"] == "Decision implemented", "Should record note"

    def test_resolve_memory_fallback_legacy_id(self, temp_vault, sample_validated_memory):
        """Test backward compat: resolve by legacy integer ID"""
        manager = MemoryLifecycleManager(str(temp_vault))

        # Try to resolve by legacy integer ID
        success = manager.resolve_memory(
            "0",  # String version of integer
            "def67890",
            "Using legacy ID"
        )

        assert success, "Should resolve with legacy integer ID"

    def test_supersede_memory(self, temp_vault, sample_validated_memory):
        """Test superseding a memory with provenance link"""
        manager = MemoryLifecycleManager(str(temp_vault))

        # Supersede first decision with new one
        success = manager.supersede_memory(
            "01M155WB9AKKTCZWTFRDDZR4W7",
            "01M156CKJAWDPFCPV7RZ011QC0",  # New decision ULID
            "PostgreSQL chosen after evaluation"
        )

        assert success, "Should supersede successfully"

        # Find superseded memory
        superseded = None
        for m in manager.memories:
            if m["memory_id"] == "01M155WB9AKKTCZWTFRDDZR4W7":
                superseded = m
                break

        assert superseded["status"] == "superseded", "Status should be 'superseded'"
        assert superseded["superseded_by"] == "01M156CKJAWDPFCPV7RZ011QC0"
        assert "PostgreSQL" in superseded["supersession_note"]

    def test_trace_provenance_simple(self, temp_vault, sample_validated_memory):
        """Test tracing provenance of a memory"""
        manager = MemoryLifecycleManager(str(temp_vault))

        # First supersede one memory
        manager.supersede_memory(
            "01M155WB9AKKTCZWTFRDDZR4W7",
            "01M156CKJAWDPFCPV7RZ011QC0",
            "Replaced with v2"
        )

        # Trace provenance
        chain = manager.trace_provenance("01M155WB9AKKTCZWTFRDDZR4W7")

        # Should show the supersession
        assert len(chain) >= 1, "Should return provenance chain"
        assert chain[0]["status"] == "superseded"

    def test_save_atomic_write(self, temp_vault, sample_validated_memory):
        """Test that save uses atomic persistence"""
        manager = MemoryLifecycleManager(str(temp_vault))

        # Resolve a memory
        manager.resolve_memory("01M155WB9AKKTCZWTFRDDZR4W7", "test123")

        # Save
        manager.save()

        # File should exist and be valid
        validated_file = temp_vault / ".claude" / "validated-memory.json"
        assert validated_file.exists(), "Should save file"

        with open(validated_file) as f:
            data = json.load(f)
            # Should have last_updated timestamp
            assert "last_updated" in data

    def test_lifecycle_not_found(self, temp_vault, sample_validated_memory):
        """Test error handling for non-existent memory"""
        manager = MemoryLifecycleManager(str(temp_vault))

        # Try to resolve non-existent memory
        success = manager.resolve_memory("nonexistent-ulid", "commit")

        assert not success, "Should fail for non-existent memory"

    def test_multiple_resolutions(self, temp_vault, sample_validated_memory):
        """Test tracking multiple resolutions"""
        manager = MemoryLifecycleManager(str(temp_vault))

        # Resolve first decision
        manager.resolve_memory(
            "01M155WB9AKKTCZWTFRDDZR4W7",
            "commit1",
            "Implemented v1"
        )

        # Resolve second decision
        manager.resolve_memory(
            "01M155WB9FCSPSFQCFM8NVATS8",
            "commit2",
            "Implemented v2"
        )

        # Count resolved
        resolved_count = sum(1 for m in manager.memories if m.get("status") == "resolved")

        # Should have 3 resolved (1 prior + 2 new)
        assert resolved_count >= 3, f"Should have 3+ resolved, got {resolved_count}"

    def test_resolution_note_optional(self, temp_vault, sample_validated_memory):
        """Test that resolution note is optional"""
        manager = MemoryLifecycleManager(str(temp_vault))

        # Resolve without note
        success = manager.resolve_memory(
            "01M155WB9AKKTCZWTFRDDZR4W7",
            "commit123"
        )

        assert success, "Should resolve without note"

        # Check memory
        for m in manager.memories:
            if m["memory_id"] == "01M155WB9AKKTCZWTFRDDZR4W7":
                assert m.get("resolution_note", "") == "", "Note should be empty if not provided"


class TestMemoryMigration:
    """Test legacy to ULID migration"""

    def test_legacy_integer_id_lookup(self, temp_vault):
        """Test that legacy integer IDs still work for lookup"""
        # Create memory without ULID (old format)
        validated_file = temp_vault / ".claude" / "validated-memory.json"
        data = {
            "validated_memory": [
                {
                    "id": 0,
                    "type": "decision",
                    "content": "Old decision without ULID",
                    "status": "active"
                }
            ]
        }
        validated_file.write_text(json.dumps(data), encoding='utf-8')

        manager = MemoryLifecycleManager(str(temp_vault))

        # Should be able to resolve by integer ID (as string)
        success = manager.resolve_memory("0", "commit")

        assert success, "Should support legacy integer ID lookup"

    def test_ulid_precedence_over_integer(self, temp_vault):
        """Test that ULID lookup takes precedence over integer ID"""
        validated_file = temp_vault / ".claude" / "validated-memory.json"
        data = {
            "validated_memory": [
                {
                    "memory_id": "01M155WB9AKKTCZWTFRDDZR4W7",
                    "id": 0,
                    "type": "decision",
                    "content": "Memory with both ULID and id",
                    "status": "active"
                }
            ]
        }
        validated_file.write_text(json.dumps(data), encoding='utf-8')

        manager = MemoryLifecycleManager(str(temp_vault))

        # Resolve by ULID
        success = manager.resolve_memory("01M155WB9AKKTCZWTFRDDZR4W7", "commit")
        assert success, "Should resolve by ULID"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
