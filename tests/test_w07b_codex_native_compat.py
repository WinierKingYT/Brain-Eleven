"""Current authenticated Codex transcript compatibility evidence for W-07B."""

from __future__ import annotations

import json

import pytest

from brain_eleven.runtime.evidence import read_increment


def _write_transcript(tmp_path, documents):
    path = tmp_path / "codex-native.jsonl"
    path.write_text(
        "".join(json.dumps(document, ensure_ascii=False) + "\n" for document in documents),
        encoding="utf-8",
    )
    return path


def test_current_codex_metadata_is_skipped_and_only_conversation_roles_become_evidence(tmp_path):
    path = _write_transcript(
        tmp_path,
        [
            {"type": "session_meta", "payload": {"session_id": "session-a"}},
            {
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "developer",
                    "content": [{"type": "input_text", "text": "DEVELOPER-TEXT-MUST-NOT-BE-EVIDENCE"}],
                },
            },
            {"type": "world_state", "payload": {"message": "WORLD-STATE-MUST-NOT-BE-EVIDENCE"}},
            {
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": "We decided to use SQLite."}],
                },
            },
            {
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": "Acknowledged."}],
                },
            },
            {"type": "token_usage_record", "payload": {"input_tokens": 10}},
        ],
    )
    stats = {}

    batch, cursor = read_increment(
        tmp_path,
        path,
        "codex",
        "session-a",
        "project-a",
        "2026-09-24T17:50:00Z",
        stats=stats,
    )

    assert [(message.record.role, message.content) for message in batch.messages] == [
        ("user", "We decided to use SQLite."),
        ("assistant", "Acknowledged."),
    ]
    assert stats == {"records_seen": 6, "conversation_records": 2, "ignored_record_types": {}}
    assert cursor["offset"] == path.stat().st_size
    rendered = json.dumps([record.to_dict() for record in batch.records])
    assert "DEVELOPER-TEXT" not in rendered
    assert "WORLD-STATE" not in rendered


def test_unknown_codex_top_level_record_still_fails_closed(tmp_path):
    path = _write_transcript(tmp_path, [{"type": "future_unknown_record", "payload": {}}])

    with pytest.raises(ValueError, match="UNSUPPORTED_CODEX_TRANSCRIPT"):
        read_increment(
            tmp_path,
            path,
            "codex",
            "session-a",
            "project-a",
            "2026-09-24T17:50:00Z",
        )
