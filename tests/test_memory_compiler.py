#!/usr/bin/env python3
"""
Brain-Eleven Memory Compiler Tests
Regression tests for Daily parsing, extraction, deduplication
"""

import pytest
import json
import tempfile
from pathlib import Path
from datetime import datetime

# Add scripts directory to path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from memory_compiler import MemoryCompiler


@pytest.fixture
def temp_vault(tmp_path):
    """Create temporary vault structure for testing"""
    vault_path = tmp_path / "test-vault"
    vault_path.mkdir()

    companion_dir = vault_path / "🔮 Companion"
    companion_dir.mkdir()

    decisions_dir = vault_path / "🗂️ Proje Notları" / "Kararlar"
    decisions_dir.mkdir(parents=True)

    return vault_path


@pytest.fixture
def sample_daily_multi_date(temp_vault):
    """Create sample Daily.md with multiple date entries"""
    daily_file = temp_vault / "🔮 Companion" / "Daily.md"

    content = """# Daily Notes - 2026-08-28

## IMPORTANT DECISION
Use PostgreSQL for production database

## LEARNED
- Microservices architecture requires careful API design
- Testing is critical before merging to main

## OPEN LOOPS
- [ ] Implement user authentication
- [ ] Add rate limiting to API

## TODAY
Started working on new feature. Made good progress on auth system.

# Daily Notes - 2026-08-29

## IMPORTANT DECISION
Decided to phase rollout in stages instead of big bang

## LEARNED
- Atomic persistence prevents data corruption
- Code review catches architectural issues early

## OPEN LOOPS
- [ ] Write regression tests
- [ ] Update documentation
- [ ] Performance profiling

## TODAY
Completed memory integrity phase. Tested with 46 memories. All systems stable.
"""

    daily_file.write_text(content, encoding='utf-8')
    return daily_file


class TestMemoryCompiler:
    """Test suite for Memory Compiler"""

    def test_extract_multi_date_entries(self, temp_vault, sample_daily_multi_date):
        """Test parsing Daily.md with multiple date entries"""
        compiler = MemoryCompiler(str(temp_vault))
        extracted = compiler.extract_from_daily()

        # Should extract from both dates
        assert extracted > 0, "No candidates extracted from multi-date Daily"

        # Should have decisions from both dates
        decisions = [c for c in compiler.candidates if c.type == "decision"]
        assert len(decisions) >= 2, f"Expected 2+ decisions, got {len(decisions)}"

    def test_source_id_format(self, temp_vault, sample_daily_multi_date):
        """Test that source_id includes date information"""
        compiler = MemoryCompiler(str(temp_vault))
        compiler.extract_from_daily()

        # All candidates should have source_id with date
        for candidate in compiler.candidates:
            assert candidate.source_id, f"Candidate missing source_id"
            # Format: daily:YYYY-MM-DD:type:idx or similar
            assert "daily:" in candidate.source_id, f"Invalid source_id format: {candidate.source_id}"
            assert candidate.source_id.count(":") >= 2, f"source_id missing date: {candidate.source_id}"

    def test_decision_extraction(self, temp_vault, sample_daily_multi_date):
        """Test IMPORTANT DECISION section extraction"""
        compiler = MemoryCompiler(str(temp_vault))
        compiler.extract_from_daily()

        decisions = [c for c in compiler.candidates if c.type == "decision"]
        assert len(decisions) >= 2, "Should extract both decisions"

        # Verify content
        decision_texts = [d.content for d in decisions]
        assert any("PostgreSQL" in t for t in decision_texts), "Should extract PostgreSQL decision"
        assert any("phase" in t.lower() for t in decision_texts), "Should extract phase decision"

    def test_lesson_extraction(self, temp_vault, sample_daily_multi_date):
        """Test LEARNED section extraction"""
        compiler = MemoryCompiler(str(temp_vault))
        compiler.extract_from_daily()

        lessons = [c for c in compiler.candidates if c.type == "lesson"]
        assert len(lessons) >= 2, f"Should extract lessons from both dates, got {len(lessons)}"

    def test_open_loop_extraction(self, temp_vault, sample_daily_multi_date):
        """Test OPEN LOOPS section extraction"""
        compiler = MemoryCompiler(str(temp_vault))
        compiler.extract_from_daily()

        loops = [c for c in compiler.candidates if c.type == "open_loop"]
        assert len(loops) >= 4, f"Should extract 4+ open loops, got {len(loops)}"

        # Verify specific tasks extracted
        loop_texts = [l.content for l in loops]
        assert any("auth" in t.lower() for t in loop_texts), "Should extract auth task"
        assert any("test" in t.lower() for t in loop_texts), "Should extract test task"

    def test_observation_extraction(self, temp_vault, sample_daily_multi_date):
        """Test TODAY section extraction"""
        compiler = MemoryCompiler(str(temp_vault))
        compiler.extract_from_daily()

        observations = [c for c in compiler.candidates if c.type == "observation"]
        assert len(observations) > 0, "Should extract observations from TODAY sections"

    def test_deduplicate_identical(self, temp_vault):
        """Test deduplication of identical candidates"""
        daily_file = temp_vault / "🔮 Companion" / "Daily.md"

        # Create Daily with duplicate content
        content = """# Daily Notes - 2026-08-29

## IMPORTANT DECISION
Use PostgreSQL for production

## IMPORTANT DECISION
Use PostgreSQL for production

## LEARNED
Important lesson here
"""
        daily_file.write_text(content, encoding='utf-8')

        compiler = MemoryCompiler(str(temp_vault))
        compiler.extract_from_daily()

        before_dedup = len(compiler.candidates)
        compiler.deduplicate()
        after_dedup = len(compiler.candidates)

        # Should remove at least one duplicate
        assert after_dedup < before_dedup, "Deduplicate should remove duplicates"

    def test_validate_and_score(self, temp_vault, sample_daily_multi_date):
        """Test quality validation and scoring"""
        compiler = MemoryCompiler(str(temp_vault))
        compiler.extract_from_daily()

        before = len(compiler.candidates)
        compiler.validate_and_score()
        after = len(compiler.candidates)

        # Should filter out low-quality candidates
        assert after <= before, "Validation should not add candidates"

        # All remaining should have confidence > 0.5
        for candidate in compiler.candidates:
            assert candidate.confidence > 0.5, f"Low confidence candidate: {candidate.confidence}"

    def test_compile_pipeline(self, temp_vault, sample_daily_multi_date):
        """Test full compilation pipeline"""
        compiler = MemoryCompiler(str(temp_vault))
        output = compiler.compile()

        # Verify output structure
        assert "compiled_at" in output
        assert "summary" in output
        assert "candidates" in output

        # Verify summary
        summary = output["summary"]
        assert summary["total_candidates"] > 0
        assert "by_type" in summary
        assert summary["by_type"]["decision"] >= 2

    def test_empty_daily(self, temp_vault):
        """Test handling of empty Daily.md"""
        daily_file = temp_vault / "🔮 Companion" / "Daily.md"
        daily_file.write_text("# Daily Notes - 2026-08-29\n", encoding='utf-8')

        compiler = MemoryCompiler(str(temp_vault))
        extracted = compiler.extract_from_daily()

        # Should handle gracefully (no crash)
        assert extracted == 0, "Empty Daily should extract 0 candidates"

    def test_malformed_sections(self, temp_vault):
        """Test handling of malformed sections"""
        daily_file = temp_vault / "🔮 Companion" / "Daily.md"

        content = """# Daily Notes - 2026-08-29

## IMPORTANT DECISION

## LEARNED
No content in decision above, should not crash

## OPEN LOOPS
- missing checkbox format
"""
        daily_file.write_text(content, encoding='utf-8')

        compiler = MemoryCompiler(str(temp_vault))

        # Should handle gracefully (no crash)
        try:
            extracted = compiler.extract_from_daily()
            assert extracted >= 0, "Should handle malformed gracefully"
        except Exception as e:
            pytest.fail(f"Compiler crashed on malformed input: {e}")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
