from __future__ import annotations

import json
from pathlib import Path

from evals.w07b import codex_native_smoke


def test_parse_stream_extracts_only_thread_and_terminal_state():
    stream = "\n".join([
        json.dumps({"type": "thread.started", "thread_id": "opaque-thread"}),
        json.dumps({"type": "item.completed", "item": {"type": "agent_message", "text": "private response"}}),
        json.dumps({"type": "turn.completed"}),
    ])

    result = codex_native_smoke._parse_stream(stream)

    assert result == {"thread_id": "opaque-thread", "turn_completed": True, "failure_code": None}
    assert "private response" not in json.dumps(result)


def test_codex_home_must_be_inside_temporary_storage(tmp_path: Path, monkeypatch):
    profile = tmp_path / ".codex"
    profile.mkdir()
    monkeypatch.setenv("CODEX_HOME", str(profile))

    assert codex_native_smoke._codex_home() == profile.resolve()


def test_codex_home_rejects_default_profile(monkeypatch):
    monkeypatch.setenv("CODEX_HOME", str(Path.home() / ".codex"))

    try:
        codex_native_smoke._codex_home()
    except RuntimeError as exc:
        assert str(exc) == "CODEX_HOME_NOT_ISOLATED"
    else:
        raise AssertionError("default Codex profile must be rejected")


def test_capture_receipt_is_bound_to_terminal_job_and_event(tmp_path: Path):
    vault = tmp_path / "vault"
    job = {"job_id": "job_opaque", "event": {"event_id": "event_opaque"}}
    receipt_path = vault / ".brain-eleven" / "runtime" / "capture-receipts" / "job_opaque.json"
    receipt_path.parent.mkdir(parents=True)
    receipt_path.write_text(json.dumps({
        "job_id": "job_opaque",
        "event_id": "event_opaque",
        "status": "EFFECT_VERIFIED",
        "canonical_verified": True,
        "review_effect_ids": ["review_opaque"],
    }), encoding="utf-8")

    assert codex_native_smoke._capture_receipt(vault, job) == {
        "status": "EFFECT_VERIFIED",
        "review_effect_ids": ["review_opaque"],
    }
    assert codex_native_smoke._capture_receipt(
        vault, {"job_id": "job_opaque", "event": {"event_id": "other_event"}}
    ) == {}
