"""SessionEnd finalization and Stop-preservation tests for IG04-B3."""

from datetime import datetime, timedelta, timezone

import pytest

from brain_eleven.projects.registry import ProjectRegistry
from brain_eleven.runtime import review_nudge
from brain_eleven.runtime.launcher import hook
from brain_eleven.runtime.storage import RuntimeConfig, read_json, write_json
from tests.test_pre13_runtime import runtime as runtime_fixture


def _add_prompts(vault, project_id, client, session_id, count):
    return [review_nudge.record_prompt(vault, client, session_id, project_id) for _ in range(count)]


def _state(vault):
    return read_json(RuntimeConfig(vault).root / "review-nudge.json")


def test_four_prompts_finalize_without_marker_and_delete_counter(runtime_fixture):
    vault, project_id = runtime_fixture
    assert all(_add_prompts(vault, project_id, "claude", "four-prompt-session", 4))

    assert review_nudge.finalize_session(vault, "claude", "four-prompt-session")
    state = _state(vault)
    assert state["counters"] == []
    assert state["markers"] == []


def test_five_prompts_create_one_content_free_marker(runtime_fixture):
    vault, project_id = runtime_fixture
    session_id = "five-prompt-session"
    assert all(_add_prompts(vault, project_id, "claude", session_id, 5))

    assert review_nudge.finalize_session(vault, "claude", session_id)
    state_path = RuntimeConfig(vault).root / "review-nudge.json"
    state_text = state_path.read_text(encoding="utf-8")
    state = read_json(state_path)
    assert state["counters"] == []
    assert len(state["markers"]) == 1
    marker = state["markers"][0]
    assert marker["schema_version"] == 1
    assert marker["project_id"] == project_id
    assert marker["prompt_count"] == 5
    assert marker["session_id_hash"] != session_id
    assert session_id not in state_text
    assert str(vault) not in state_text


def test_duplicate_session_end_is_idempotent(runtime_fixture):
    vault, project_id = runtime_fixture
    _add_prompts(vault, project_id, "codex", "duplicate-end-session", 5)

    assert review_nudge.finalize_session(vault, "codex", "duplicate-end-session")
    before = _state(vault)["markers"]
    assert review_nudge.finalize_session(vault, "codex", "duplicate-end-session")
    after = _state(vault)["markers"]

    assert len(before) == len(after) == 1
    assert before == after


def test_stop_never_mutates_the_counter(runtime_fixture, monkeypatch):
    vault, project_id = runtime_fixture
    session_id = "stop-preserves-session"
    _add_prompts(vault, project_id, "claude", session_id, 4)
    monkeypatch.setattr("brain_eleven.runtime.worker.enqueue", lambda *_args, **_kwargs: {"status": "QUEUED"})
    monkeypatch.setattr("brain_eleven.runtime.launcher.ensure_service", lambda *_args, **_kwargs: True)
    payload = {"cwd": str(vault), "session_id": session_id, "transcript_path": "unused"}
    before = _state(vault)

    assert hook(vault, "claude", "Stop", payload) == {}
    assert hook(vault, "claude", "Stop", payload) == {}
    assert _state(vault) == before


def test_session_end_finalizes_every_project_even_after_cwd_changes(runtime_fixture, tmp_path):
    vault, first_project_id = runtime_fixture
    other_root = tmp_path / "other-project"
    other_root.mkdir()
    other = ProjectRegistry(vault).register(other_root, proactive_capture=True)
    config = RuntimeConfig(vault).load()
    config["project_ids"].append(other["project_id"])
    write_json(RuntimeConfig(vault).path, config)
    session_id = "changed-cwd-session"
    _add_prompts(vault, first_project_id, "codex", session_id, 5)
    _add_prompts(vault, other["project_id"], "codex", session_id, 6)
    unregistered_cwd = tmp_path / "unregistered-current-directory"
    unregistered_cwd.mkdir()

    # The current cwd is not eligible, so the old B1 queue path returns early;
    # B3 still finalizes the stored project counters first.
    assert hook(vault, "codex", "SessionEnd", {
        "cwd": str(unregistered_cwd),
        "session_id": session_id,
    }) == {}
    markers = _state(vault)["markers"]
    assert {row["project_id"] for row in markers} == {first_project_id, other["project_id"]}
    assert _state(vault)["counters"] == []


def test_session_end_finalization_survives_queue_failure(runtime_fixture, monkeypatch):
    vault, project_id = runtime_fixture
    session_id = "queue-failure-session"
    _add_prompts(vault, project_id, "claude", session_id, 5)
    monkeypatch.setattr(
        "brain_eleven.runtime.worker.enqueue",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("simulated queue failure")),
    )

    with pytest.raises(OSError, match="simulated queue failure"):
        hook(vault, "claude", "SessionEnd", {"cwd": str(vault), "session_id": session_id})

    assert len(_state(vault)["markers"]) == 1


def test_session_end_removes_counter_if_project_is_no_longer_opted_in(runtime_fixture):
    vault, project_id = runtime_fixture
    session_id = "revoked-opt-in-session"
    _add_prompts(vault, project_id, "claude", session_id, 5)
    ProjectRegistry(vault).set_proactive_capture(project_id, False)

    assert review_nudge.finalize_session(vault, "claude", session_id)
    state = _state(vault)
    assert state["counters"] == []
    assert state["markers"] == []


def test_expired_counter_never_creates_marker(runtime_fixture):
    vault, project_id = runtime_fixture
    session_id = "expired-counter-session"
    _add_prompts(vault, project_id, "codex", session_id, 5)
    path = RuntimeConfig(vault).root / "review-nudge.json"
    ledger = read_json(path)
    expired = datetime.now(timezone.utc) - timedelta(days=8)
    ledger["counters"][0]["last_seen_at"] = expired.isoformat().replace("+00:00", "Z")
    ledger["counters"][0]["expires_at"] = (expired + timedelta(days=7)).isoformat().replace("+00:00", "Z")
    write_json(path, ledger)

    assert review_nudge.finalize_session(vault, "codex", session_id)
    state = _state(vault)
    assert state["counters"] == []
    assert state["markers"] == []


def test_off_mode_suppresses_session_end_finalization(runtime_fixture):
    vault, project_id = runtime_fixture
    session_id = "off-finalization-session"
    _add_prompts(vault, project_id, "claude", session_id, 5)
    RuntimeConfig(vault).set_mode("OFF")

    assert not review_nudge.finalize_session(vault, "claude", session_id)
    state = _state(vault)
    assert len(state["counters"]) == 1
    assert state["markers"] == []
