#!/usr/bin/env python3
"""
Phase 10A/10B: Summarizer & Anomaly Detector Tests

Both modules are deliberately embedding/LLM-free (token-overlap + metadata
rules), so tests use synthetic fixtures rather than the real vault - keeps
them deterministic and independent of what's currently stored.
"""

import sys
import json
from pathlib import Path
from datetime import datetime, timedelta

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from summarizer import MemorySummarizer, tokenize, jaccard_similarity  # noqa: E402
from anomaly_detector import AnomalyDetector  # noqa: E402


def make_memory(**overrides):
    """Build a minimally valid memory dict, overriding fields as needed."""
    base = {
        "memory_id": "01TEST0000000000000000000",
        "id": 0,
        "source_id": "daily:2026-08-28:observation:0:0",
        "type": "observation",
        "content": "Some memory content",
        "confidence": 0.8,
        "source": "daily",
        "timestamp": "2026-08-28T12:00:00",
        "quality_score": 0.8,
        "status": "active",
        "is_approved": True,
        "superseded_by": "",
    }
    base.update(overrides)
    return base


@pytest.fixture
def vault(tmp_path):
    """Isolated vault dir with a .claude/validated-memory.json we control."""
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir()
    return tmp_path


def write_memories(vault_path, memories):
    claude_dir = vault_path / ".claude"
    claude_dir.mkdir(exist_ok=True)
    with open(claude_dir / "validated-memory.json", "w", encoding="utf-8") as f:
        json.dump({"validated_memory": memories}, f)


# ---------------------------------------------------------------------------
# Tokenize / Jaccard helpers
# ---------------------------------------------------------------------------

class TestTextHelpers:

    def test_tokenize_lowercases_and_strips_stopwords(self):
        # Act
        tokens = tokenize("The Quick Brown Fox and the Lazy Dog")

        # Assert
        assert "the" not in tokens
        assert "and" not in tokens
        assert "quick" in tokens
        assert "fox" in tokens

    def test_jaccard_identical_strings_is_one(self):
        # Act
        score = jaccard_similarity("hello world foo", "hello world foo")

        # Assert
        assert score == pytest.approx(1.0)

    def test_jaccard_disjoint_strings_is_zero(self):
        # Act
        score = jaccard_similarity("apples oranges", "trucks planes")

        # Assert
        assert score == 0.0

    def test_jaccard_empty_string_is_zero(self):
        # Act
        score = jaccard_similarity("", "something")

        # Assert
        assert score == 0.0


# ---------------------------------------------------------------------------
# MemorySummarizer (Phase 10A)
# ---------------------------------------------------------------------------

class TestMemorySummarizer:

    def test_load_memories_returns_empty_list_when_no_file(self, vault):
        # Arrange
        summarizer = MemorySummarizer(vault_path=str(vault))

        # Act
        result = summarizer.load_memories()

        # Assert
        assert result == []

    def test_load_memories_filters_by_status(self, vault):
        # Arrange
        write_memories(vault, [
            make_memory(memory_id="a", status="active"),
            make_memory(memory_id="b", status="resolved"),
            make_memory(memory_id="c", status="superseded"),
        ])
        summarizer = MemorySummarizer(vault_path=str(vault))

        # Act
        result = summarizer.load_memories(statuses=["active"])

        # Assert
        assert len(result) == 1
        assert result[0]["memory_id"] == "a"

    def test_extract_date_from_source_id(self):
        # Arrange
        mem = make_memory(source_id="daily:2026-08-28:observation:0:0")

        # Act
        date = MemorySummarizer.extract_date(mem)

        # Assert
        assert date == "2026-08-28"

    def test_extract_date_falls_back_to_timestamp(self):
        # Arrange
        mem = make_memory(source_id="", timestamp="2026-08-29T10:00:00")

        # Act
        date = MemorySummarizer.extract_date(mem)

        # Assert
        assert date == "2026-08-29"

    def test_rank_score_weights_quality_and_confidence(self):
        # Arrange
        mem = make_memory(quality_score=1.0, confidence=0.5)

        # Act
        score = MemorySummarizer.rank_score(mem)

        # Assert: 1.0*0.6 + 0.5*0.4 = 0.8
        assert score == pytest.approx(0.8)

    def test_dedupe_similar_keeps_only_highest_ranked_duplicate(self, vault):
        # Arrange
        summarizer = MemorySummarizer(vault_path=str(vault))
        memories = [
            make_memory(memory_id="low", content="Fixed the login bug today", confidence=0.5, quality_score=0.5),
            make_memory(memory_id="high", content="Fixed the login bug today", confidence=0.9, quality_score=0.9),
        ]

        # Act
        deduped = summarizer.dedupe_similar(memories)

        # Assert
        assert len(deduped) == 1
        assert deduped[0]["memory_id"] == "high"

    def test_dedupe_keeps_dissimilar_memories(self, vault):
        # Arrange
        summarizer = MemorySummarizer(vault_path=str(vault))
        memories = [
            make_memory(memory_id="a", content="Fixed the login bug today"),
            make_memory(memory_id="b", content="Deployed the API to production"),
        ]

        # Act
        deduped = summarizer.dedupe_similar(memories)

        # Assert
        assert len(deduped) == 2

    def test_generate_digest_groups_by_type_and_dedupes(self, vault):
        # Arrange
        write_memories(vault, [
            make_memory(memory_id="a", type="decision", content="Chose FastAPI for the API layer"),
            make_memory(memory_id="b", type="decision", content="Chose FastAPI for the API layer"),
            make_memory(memory_id="c", type="lesson", content="Always write tests first"),
        ])
        summarizer = MemorySummarizer(vault_path=str(vault))

        # Act
        digest = summarizer.generate_digest()

        # Assert
        assert digest["total_memories_considered"] == 3
        assert len(digest["by_type"]["decision"]) == 1  # deduped
        assert len(digest["by_type"]["lesson"]) == 1

    def test_generate_digest_respects_days_filter(self, vault):
        # Arrange
        old_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
        recent_date = datetime.now().strftime("%Y-%m-%d")
        write_memories(vault, [
            make_memory(memory_id="old", source_id=f"daily:{old_date}:observation:0:0"),
            make_memory(memory_id="new", source_id=f"daily:{recent_date}:observation:0:1", content="Different content entirely"),
        ])
        summarizer = MemorySummarizer(vault_path=str(vault))

        # Act
        digest = summarizer.generate_digest(days=7)

        # Assert
        assert digest["total_memories_considered"] == 1

    def test_to_markdown_produces_readable_report(self, vault):
        # Arrange
        write_memories(vault, [make_memory()])
        summarizer = MemorySummarizer(vault_path=str(vault))
        digest = summarizer.generate_digest()

        # Act
        markdown = summarizer.to_markdown(digest)

        # Assert
        assert "# Memory Digest" in markdown
        assert "Observation" in markdown


# ---------------------------------------------------------------------------
# AnomalyDetector (Phase 10B)
# ---------------------------------------------------------------------------

class TestAnomalyDetector:

    def test_detect_all_returns_empty_report_for_clean_data(self, vault):
        # Arrange
        write_memories(vault, [
            make_memory(memory_id="a", content="A perfectly normal memory entry here"),
        ])
        detector = AnomalyDetector(vault_path=str(vault))

        # Act
        report = detector.detect_all()

        # Assert
        assert report["total_anomalies"] == 0

    def test_detects_duplicate_content(self, vault):
        # Arrange
        memories = [
            make_memory(memory_id="a", content="Deployed the search API to production"),
            make_memory(memory_id="b", content="Deployed the search API to production"),
        ]
        detector = AnomalyDetector(vault_path=str(vault))

        # Act
        anomalies = detector.detect_duplicate_content(memories)

        # Assert
        assert len(anomalies) == 1
        assert anomalies[0]["type"] == "duplicate_content"
        assert set(anomalies[0]["memory_ids"]) == {"a", "b"}

    def test_ignores_duplicates_across_different_types(self, vault):
        # Arrange
        memories = [
            make_memory(memory_id="a", type="decision", content="Deployed the search API"),
            make_memory(memory_id="b", type="lesson", content="Deployed the search API"),
        ]
        detector = AnomalyDetector(vault_path=str(vault))

        # Act
        anomalies = detector.detect_duplicate_content(memories)

        # Assert
        assert anomalies == []

    def test_detects_stale_open_loop(self, vault):
        # Arrange
        old_timestamp = (datetime.now() - timedelta(days=10)).isoformat()
        memories = [
            make_memory(memory_id="a", type="open_loop", status="active", timestamp=old_timestamp),
        ]
        detector = AnomalyDetector(vault_path=str(vault))

        # Act
        anomalies = detector.detect_stale_open_loops(memories)

        # Assert
        assert len(anomalies) == 1
        assert anomalies[0]["type"] == "stale_open_loop"

    def test_does_not_flag_recent_open_loop(self, vault):
        # Arrange
        recent_timestamp = datetime.now().isoformat()
        memories = [
            make_memory(memory_id="a", type="open_loop", status="active", timestamp=recent_timestamp),
        ]
        detector = AnomalyDetector(vault_path=str(vault))

        # Act
        anomalies = detector.detect_stale_open_loops(memories)

        # Assert
        assert anomalies == []

    def test_does_not_flag_resolved_open_loop_as_stale(self, vault):
        # Arrange
        old_timestamp = (datetime.now() - timedelta(days=10)).isoformat()
        memories = [
            make_memory(memory_id="a", type="open_loop", status="resolved", timestamp=old_timestamp),
        ]
        detector = AnomalyDetector(vault_path=str(vault))

        # Act
        anomalies = detector.detect_stale_open_loops(memories)

        # Assert
        assert anomalies == []

    def test_detects_low_confidence_outlier(self, vault):
        # Arrange
        memories = [make_memory(memory_id="a", is_approved=True, confidence=0.1)]
        detector = AnomalyDetector(vault_path=str(vault))

        # Act
        anomalies = detector.detect_low_confidence_outliers(memories)

        # Assert
        assert len(anomalies) == 1

    def test_detects_quality_confidence_gap(self, vault):
        # Arrange
        memories = [make_memory(memory_id="a", quality_score=0.95, confidence=0.2)]
        detector = AnomalyDetector(vault_path=str(vault))

        # Act
        anomalies = detector.detect_quality_confidence_gap(memories)

        # Assert
        assert len(anomalies) == 1

    def test_detects_burst_ingestion(self, vault):
        # Arrange
        same_ts = "2026-08-29T12:00:00"
        memories = [
            make_memory(memory_id=f"m{i}", timestamp=same_ts, content=f"content {i}")
            for i in range(20)
        ]
        detector = AnomalyDetector(vault_path=str(vault))

        # Act
        anomalies = detector.detect_burst_ingestion(memories)

        # Assert
        assert len(anomalies) == 1
        assert anomalies[0]["details"]["count"] == 20

    def test_does_not_flag_normal_ingestion_rate(self, vault):
        # Arrange
        memories = [
            make_memory(memory_id=f"m{i}", timestamp=f"2026-08-29T12:00:0{i}")
            for i in range(5)
        ]
        detector = AnomalyDetector(vault_path=str(vault))

        # Act
        anomalies = detector.detect_burst_ingestion(memories)

        # Assert
        assert anomalies == []

    def test_detects_broken_supersession(self, vault):
        # Arrange
        memories = [
            make_memory(memory_id="a", superseded_by="does-not-exist"),
        ]
        detector = AnomalyDetector(vault_path=str(vault))

        # Act
        anomalies = detector.detect_broken_supersession(memories)

        # Assert
        assert len(anomalies) == 1
        assert anomalies[0]["severity"] == "critical"

    def test_valid_supersession_is_not_flagged(self, vault):
        # Arrange
        memories = [
            make_memory(memory_id="a", superseded_by="b"),
            make_memory(memory_id="b"),
        ]
        detector = AnomalyDetector(vault_path=str(vault))

        # Act
        anomalies = detector.detect_broken_supersession(memories)

        # Assert
        assert anomalies == []

    def test_detects_trivial_content(self, vault):
        # Arrange
        memories = [make_memory(memory_id="a", content="ok")]
        detector = AnomalyDetector(vault_path=str(vault))

        # Act
        anomalies = detector.detect_trivial_content(memories)

        # Assert
        assert len(anomalies) == 1

    def test_detect_all_sorts_by_severity(self, vault):
        # Arrange: one critical (broken supersession), one info (trivial content)
        memories = [
            make_memory(memory_id="a", superseded_by="missing"),
            make_memory(memory_id="b", content="ok", timestamp="2026-08-29T09:00:00"),
        ]
        write_memories(vault, memories)
        detector = AnomalyDetector(vault_path=str(vault))

        # Act
        report = detector.detect_all()

        # Assert: critical anomalies come first
        assert report["anomalies"][0]["severity"] == "critical"

    def test_to_markdown_reports_no_anomalies_cleanly(self, vault):
        # Arrange
        write_memories(vault, [make_memory(content="A perfectly normal entry")])
        detector = AnomalyDetector(vault_path=str(vault))
        report = detector.detect_all()

        # Act
        markdown = detector.to_markdown(report)

        # Assert
        assert "No anomalies detected" in markdown
