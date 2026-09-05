"""PRE-03 evidence-reader and zero-retention contract tests."""

from __future__ import annotations

import json

import pytest

from evidence import (
    DailyEvidenceAdapter,
    EvidenceCorruptError,
    EvidencePathError,
    EvidenceStore,
    TranscriptReader,
)


def _write_jsonl(path, records):
    path.write_text("\n".join(json.dumps(record) for record in records) + "\n", encoding="utf-8")


def test_transcript_reader_preserves_roles_and_persists_metadata_without_raw_content(tmp_path):
    transcript = tmp_path / "session.jsonl"
    user_text = "The raw user statement must never enter durable evidence metadata."
    assistant_text = "The assistant proposal remains role-attributed evidence."
    _write_jsonl(
        transcript,
        [
            {"role": "user", "message": {"content": user_text}, "timestamp": "2026-08-28T10:00:00Z"},
            {"type": "assistant", "message": {"content": assistant_text}, "timestamp": "2026-08-28T10:01:00Z"},
            {"type": "tool", "message": {"content": "tool result"}},
        ],
    )

    batch = TranscriptReader().read(
        transcript,
        session_id="session_01",
        project_id="proj_evidence",
        captured_at="2026-09-04T10:00:00Z",
    )
    EvidenceStore(tmp_path / "vault").persist(batch.records)

    assert [record.role for record in batch.records] == ["user", "assistant", "tool"]
    assert [message.content for message in batch.messages] == [user_text, assistant_text, "tool result"]
    first = batch.records[0]
    assert first.occurred_at.value == "2026-08-28T10:00:00Z"
    assert first.occurred_at.precision == "instant"
    assert first.captured_at == "2026-09-04T10:00:00Z"
    assert first.retention == {"raw_retained": False, "expires_at": None}
    persisted = "".join(
        path.read_text(encoding="utf-8")
        for path in (tmp_path / "vault" / ".brain-eleven" / "capture" / "evidence").glob("*.json")
    )
    assert user_text not in persisted
    assert assistant_text not in persisted
    assert "path_hash" in persisted
    assert "content_hash" in persisted


def test_reprocessing_identical_evidence_is_idempotent(tmp_path):
    transcript = tmp_path / "session.jsonl"
    _write_jsonl(transcript, [{"role": "user", "content": "A durable source statement.", "timestamp": "2026-09-01T10:00:00Z"}])
    reader = TranscriptReader()
    first = reader.read(transcript, session_id="session_01", project_id="proj_x", captured_at="2026-09-04T10:00:00Z")
    second = reader.read(transcript, session_id="session_01", project_id="proj_x", captured_at="2026-09-04T10:00:00Z")
    store = EvidenceStore(tmp_path / "vault")

    store.persist(first.records)
    store.persist(second.records)

    assert first.records[0].evidence_id == second.records[0].evidence_id
    assert len(list((tmp_path / "vault" / ".brain-eleven" / "capture" / "evidence").glob("*.json"))) == 1


def test_daily_adapter_retains_day_precision_without_inventing_an_instant(tmp_path):
    daily = tmp_path / "Daily.md"
    daily.write_text(
        "# Daily Notes - 2026-08-28\n## IMPORTANT DECISION\nSQLite is local persistence.\n\n# Daily Notes - 2026-08-29\n## LEARNED\nKeep evidence separate.\n",
        encoding="utf-8",
    )

    batch = DailyEvidenceAdapter().read(daily, project_id="proj_daily", captured_at="2026-09-04T10:00:00Z")

    assert len(batch.records) == 2
    assert batch.records[0].source_type == "DAILY_NOTE"
    assert batch.records[0].occurred_at.value == "2026-08-28"
    assert batch.records[0].occurred_at.precision == "day"


def test_reader_rejects_invalid_jsonl_changed_or_oversized_sources_fail_closed(tmp_path):
    invalid = tmp_path / "invalid.jsonl"
    invalid.write_text("{not json\n", encoding="utf-8")
    with pytest.raises(EvidenceCorruptError) as exc:
        TranscriptReader().read(invalid, session_id="session_01", project_id=None)
    assert exc.value.code == "EVIDENCE_CORRUPT"

    oversized = tmp_path / "oversized.jsonl"
    oversized.write_text("x" * 32, encoding="utf-8")
    with pytest.raises(EvidencePathError) as exc:
        TranscriptReader(maximum_bytes=16).read(oversized, session_id="session_01", project_id=None)
    assert exc.value.code == "TRANSCRIPT_INVALID"


def test_evidence_reading_and_metadata_persistence_never_write_canonical_memory_or_state(tmp_path):
    transcript = tmp_path / "session.jsonl"
    _write_jsonl(transcript, [{"role": "user", "content": "A current observed fact."}])
    vault = tmp_path / "vault"
    batch = TranscriptReader().read(transcript, session_id="session_01", project_id=None)

    EvidenceStore(vault).persist(batch.records)

    assert not (vault / ".claude" / "validated-memory.json").exists()
    assert not (vault / ".claude" / "project-state.json").exists()
