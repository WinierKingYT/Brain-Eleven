"""PRE-01 hook-event contract tests: bounded, deterministic and side-effect free."""

from __future__ import annotations

import json

import pytest

from capture_event import (
    MAX_HOOK_EVENT_BYTES,
    CaptureEventError,
    CaptureProjectResolutionError,
    parse_hook_event,
    parse_hook_event_json,
)
from project_registry import ProjectRegistry


def _session_event(project_root: str) -> dict:
    return {
        "event_type": "SESSION_END",
        "session_id": "session_01J0000000000000000000000",
        "project_root": project_root,
        "event_at": "2026-09-05T13:00:00+03:00",
        "transcript_path": "C:/Users/faruk/.claude/projects/example.jsonl",
    }


def test_session_end_event_resolves_known_project_without_writing_canonical_stores(tmp_path):
    vault = tmp_path / "vault"
    project_root = tmp_path / "project"
    registry = ProjectRegistry(vault)
    record = registry.register(project_root, project_id="proj_capture")
    registry_before = registry.path.read_text(encoding="utf-8")

    event = parse_hook_event(_session_event(str(project_root)), vault_path=vault)

    assert event.project_id == record["project_id"]
    assert event.project_status == "resolved"
    assert event.event_at == "2026-09-05T10:00:00Z"
    assert event.idempotency_key == "session:session_01J0000000000000000000000:end"
    assert registry.path.read_text(encoding="utf-8") == registry_before
    assert not (vault / ".claude" / "validated-memory.json").exists()
    assert not (vault / ".brain-eleven" / "state" / "state-store.json").exists()


def test_duplicate_session_end_events_have_the_same_stable_identity(tmp_path):
    payload = _session_event(str(tmp_path / "unknown-project"))

    first = parse_hook_event(payload, vault_path=tmp_path / "vault")
    second = parse_hook_event(dict(payload), vault_path=tmp_path / "vault")

    assert first.event_id == second.event_id
    assert first.idempotency_key == second.idempotency_key
    assert first.project_id is None
    assert first.project_status == "unresolved"
    assert not (tmp_path / "vault").exists()


def test_prompt_events_hash_raw_content_but_never_serialize_it(tmp_path):
    raw_prompt = "Use the exact phrase only in this transient hook payload."
    payload = {
        "event_type": "USER_PROMPT_SUBMIT",
        "session_id": "session_01J0000000000000000000000",
        "project_root": str(tmp_path / "unknown"),
        "event_at": "2026-09-05T10:00:00Z",
        "prompt": raw_prompt,
    }

    first = parse_hook_event(payload, vault_path=tmp_path / "vault")
    second = parse_hook_event(dict(payload), vault_path=tmp_path / "vault")
    rendered = json.dumps(first.to_dict(), ensure_ascii=False)

    assert first.event_id == second.event_id
    assert first.prompt_sha256 is not None
    assert first.prompt_length == len(raw_prompt)
    assert raw_prompt not in rendered
    assert "prompt_sha256" not in rendered
    assert first.prompt_sha256 in rendered


def test_prompt_metadata_is_accepted_without_requiring_raw_prompt(tmp_path):
    payload = {
        "event_type": "USER_PROMPT_SUBMIT",
        "session_id": "session_01J0000000000000000000000",
        "project_root": str(tmp_path / "unknown"),
        "event_at": "2026-09-05T10:00:00Z",
        "prompt_sha256": "sha256:" + ("a" * 64),
        "prompt_length": 42,
    }

    event = parse_hook_event(payload, vault_path=tmp_path / "vault")

    assert event.prompt_sha256 == payload["prompt_sha256"]
    assert event.prompt_length == 42


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"event_type": "UNKNOWN"},
        {
            "event_type": "SESSION_END",
            "session_id": "bad session id",
            "project_root": "C:/project",
            "event_at": "2026-09-05T10:00:00Z",
            "transcript_path": "C:/transcript.jsonl",
        },
        {
            "event_type": "SESSION_END",
            "session_id": "session_01",
            "project_root": "C:/project",
            "event_at": "2026-09-05T10:00:00Z",
            "transcript_path": "C:/transcript.jsonl",
            "project_id": "untrusted-override",
        },
        {
            "event_type": "USER_PROMPT_SUBMIT",
            "session_id": "session_01",
            "project_root": "C:/project",
            "event_at": "2026-09-05T10:00:00Z",
            "prompt": "one",
            "prompt_sha256": "sha256:" + ("a" * 64),
        },
    ],
)
def test_malformed_or_untrusted_event_fields_fail_closed(tmp_path, payload):
    with pytest.raises(CaptureEventError) as exc:
        parse_hook_event(payload, vault_path=tmp_path / "vault")

    assert exc.value.code == "CAPTURE_EVENT_INVALID"
    assert not (tmp_path / "vault" / ".claude" / "validated-memory.json").exists()


def test_stdin_parser_rejects_invalid_json_and_bounded_oversize_payload(tmp_path):
    with pytest.raises(CaptureEventError, match="UTF-8 JSON"):
        parse_hook_event_json("{not json", vault_path=tmp_path / "vault")
    with pytest.raises(CaptureEventError, match="exceeds"):
        parse_hook_event_json(b"x" * (MAX_HOOK_EVENT_BYTES + 1), vault_path=tmp_path / "vault")


def test_corrupt_registry_fails_closed_instead_of_becoming_an_unknown_project(tmp_path):
    vault = tmp_path / "vault"
    path = vault / ".claude" / "project-registry.json"
    path.parent.mkdir(parents=True)
    path.write_text("{not valid json", encoding="utf-8")
    before = path.read_text(encoding="utf-8")

    with pytest.raises(CaptureProjectResolutionError) as exc:
        parse_hook_event(_session_event(str(tmp_path / "project")), vault_path=vault)

    assert exc.value.code == "PROJECT_REGISTRY_UNAVAILABLE"
    assert path.read_text(encoding="utf-8") == before


def test_archived_project_is_resolved_as_archived_without_reactivation(tmp_path):
    vault = tmp_path / "vault"
    project_root = tmp_path / "project"
    registry = ProjectRegistry(vault)
    registry.register(project_root, project_id="proj_archived")
    registry.set_status("proj_archived", "archived")

    event = parse_hook_event(_session_event(str(project_root)), vault_path=vault)

    assert event.project_id == "proj_archived"
    assert event.project_status == "archived"
    assert registry.get("proj_archived")["status"] == "archived"
