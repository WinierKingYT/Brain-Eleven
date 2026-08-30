#!/usr/bin/env python3
"""
Phase 12: Post-Session Maintenance Tests

Covers the orchestration logic (report building, non-fatal step isolation,
surface-threshold decision) with synthetic fixtures - same pattern as
Phase 10/11 tests, independent of the real vault's current contents.
"""

import sys
import json
from pathlib import Path
from datetime import datetime, timedelta

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from post_session_maintenance import (  # noqa: E402
    run_maintenance, save_report, summarize_for_shell, SURFACE_THRESHOLD,
)


def make_memory(**overrides):
    base = {
        "memory_id": "01TEST0000000000000000000",
        "source_id": "daily:2026-08-28:observation:0:0",
        "type": "observation",
        "content": "Some memory content",
        "confidence": 0.8,
        "timestamp": datetime.now().isoformat(),
        "quality_score": 0.8,
        "status": "active",
        "is_approved": True,
        "superseded_by": "",
    }
    base.update(overrides)
    return base


def write_memories(vault_path, memories):
    claude_dir = vault_path / ".claude"
    claude_dir.mkdir(exist_ok=True)
    with open(claude_dir / "validated-memory.json", "w", encoding="utf-8") as f:
        json.dump({"validated_memory": memories}, f)


@pytest.fixture
def vault(tmp_path):
    (tmp_path / ".claude").mkdir()
    return tmp_path


class TestRunMaintenance:

    def test_all_steps_succeed_on_clean_vault(self, vault):
        write_memories(vault, [make_memory(content="A perfectly normal unique entry")])

        report = run_maintenance(str(vault))

        assert report["graph"]["ok"] is True
        assert report["anomalies"]["ok"] is True
        assert report["digest"]["ok"] is True

    def test_empty_vault_does_not_crash(self, vault):
        report = run_maintenance(str(vault))

        assert report["graph"]["ok"] is True
        assert report["anomalies"]["ok"] is True
        assert report["digest"]["ok"] is True
        assert report["graph"]["data"]["total_entities"] == 0

    def test_surface_flag_true_when_anomalies_found(self, vault):
        write_memories(vault, [
            make_memory(memory_id="a", content="Deployed the search API to production"),
            make_memory(memory_id="b", content="Deployed the search API to production"),
        ])

        report = run_maintenance(str(vault))

        assert report["anomalies"]["data"]["total_anomalies"] >= SURFACE_THRESHOLD
        assert report["surface_at_next_session"] is True

    def test_surface_flag_false_on_clean_vault(self, vault):
        write_memories(vault, [make_memory(content="A perfectly normal unique entry")])

        report = run_maintenance(str(vault))

        assert report["surface_at_next_session"] is False

    def test_one_failing_step_does_not_block_others(self, vault, monkeypatch):
        write_memories(vault, [make_memory(content="Something to summarize")])

        import post_session_maintenance as psm

        def broken_extractor(_vault_path):
            raise RuntimeError("simulated graph failure")

        monkeypatch.setattr(psm, "EntityExtractor", broken_extractor)

        report = run_maintenance(str(vault))

        assert report["graph"]["ok"] is False
        assert "simulated graph failure" in report["graph"]["error"]
        # The other two steps must still have run despite the graph step blowing up.
        assert report["anomalies"]["ok"] is True
        assert report["digest"]["ok"] is True

    def test_malformed_memory_file_does_not_crash_maintenance(self, vault):
        claude_dir = vault / ".claude"
        claude_dir.mkdir(exist_ok=True)
        (claude_dir / "validated-memory.json").write_text("{not valid json", encoding="utf-8")

        report = run_maintenance(str(vault))

        # Every step should report failure gracefully rather than raising
        # out of run_maintenance itself.
        for step in ("graph", "anomalies", "digest"):
            assert isinstance(report[step]["ok"], bool)


class TestSaveReport:

    def test_save_report_writes_valid_json(self, vault):
        report = run_maintenance(str(vault))

        report_path = save_report(report, str(vault))

        assert report_path.exists()
        with open(report_path, encoding="utf-8") as f:
            loaded = json.load(f)
        assert loaded["generated_at"] == report["generated_at"]

    def test_save_report_is_atomic_no_leftover_tmp_file(self, vault):
        report = run_maintenance(str(vault))

        report_path = save_report(report, str(vault))

        assert not report_path.with_suffix(".tmp").exists()

    def test_save_report_overwrites_prior_report(self, vault):
        first = run_maintenance(str(vault))
        save_report(first, str(vault))

        write_memories(vault, [make_memory(content="New content after first save")])
        second = run_maintenance(str(vault))
        report_path = save_report(second, str(vault))

        with open(report_path, encoding="utf-8") as f:
            loaded = json.load(f)
        assert loaded["generated_at"] == second["generated_at"]


class TestSummarizeForShell:

    def test_summary_reports_ok_steps(self, vault):
        write_memories(vault, [make_memory(content="A perfectly normal unique entry")])
        report = run_maintenance(str(vault))

        summary = summarize_for_shell(report)

        assert "Graph: OK" in summary
        assert "Anomalies: OK" in summary
        assert "Digest: OK" in summary

    def test_summary_reports_clean_vs_found_anomalies(self, vault):
        write_memories(vault, [make_memory(content="A perfectly normal unique entry")])
        clean_report = run_maintenance(str(vault))

        write_memories(vault, [
            make_memory(memory_id="a", content="Deployed the search API to production"),
            make_memory(memory_id="b", content="Deployed the search API to production"),
        ])
        dirty_report = run_maintenance(str(vault))

        assert "clean" in summarize_for_shell(clean_report).lower()
        assert "found" in summarize_for_shell(dirty_report).lower()

    def test_summary_reports_failed_step(self, vault, monkeypatch):
        import post_session_maintenance as psm

        def broken_extractor(_vault_path):
            raise RuntimeError("boom")

        monkeypatch.setattr(psm, "EntityExtractor", broken_extractor)
        report = run_maintenance(str(vault))

        summary = summarize_for_shell(report)

        assert "Graph: FAILED" in summary
