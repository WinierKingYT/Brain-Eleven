"""Per-session prompt counting for the IG04-B3 review nudge."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

from brain_eleven.projects.registry import ProjectRegistry
from brain_eleven.runtime import review_nudge
from brain_eleven.runtime.launcher import hook
from brain_eleven.runtime.storage import RuntimeConfig, read_json, write_json
from tests.test_pre13_runtime import runtime as runtime_fixture


def test_counter_is_session_and_project_scoped_and_content_free(runtime_fixture):
    vault, project_id = runtime_fixture
    other_root = vault.parent / "other-project"
    other_root.mkdir()
    other = ProjectRegistry(vault).register(other_root, proactive_capture=True)
    config = RuntimeConfig(vault).load()
    config["project_ids"].append(other["project_id"])
    write_json(RuntimeConfig(vault).path, config)
    session_id = "counter-session-01"

    assert review_nudge.record_prompt(vault, "claude", session_id, project_id)
    assert review_nudge.record_prompt(vault, "claude", session_id, project_id)
    assert review_nudge.record_prompt(vault, "claude", session_id, other["project_id"])
    assert review_nudge.record_prompt(vault, "codex", session_id, project_id)

    state_path = RuntimeConfig(vault).root / "review-nudge.json"
    state_text = state_path.read_text(encoding="utf-8")
    state = read_json(state_path)
    assert len(state["counters"]) == 3
    assert {row["prompt_count"] for row in state["counters"]} == {1, 2}
    assert session_id not in state_text
    assert str(vault) not in state_text
    assert all(row["project_id"] in {project_id, other["project_id"]} for row in state["counters"])


def test_invalid_session_unknown_project_and_opt_out_do_not_count(runtime_fixture):
    vault, project_id = runtime_fixture
    assert not review_nudge.record_prompt(vault, "claude", "bad session id", project_id)
    assert not review_nudge.record_prompt(vault, "claude", "valid-session", "unknown-project")

    ProjectRegistry(vault).set_proactive_capture(project_id, False)
    assert not review_nudge.record_prompt(vault, "claude", "valid-session", project_id)
    assert not (RuntimeConfig(vault).root / "review-nudge.json").exists()


def test_off_mode_suppresses_counter(runtime_fixture):
    vault, project_id = runtime_fixture
    RuntimeConfig(vault).set_mode("OFF")

    assert not review_nudge.record_prompt(vault, "claude", "off-session", project_id)
    assert not (RuntimeConfig(vault).root / "review-nudge.json").exists()


def test_concurrent_prompts_do_not_lose_increments(runtime_fixture):
    vault, project_id = runtime_fixture
    session_id = "concurrent-session"

    with ThreadPoolExecutor(max_workers=12) as pool:
        results = list(pool.map(
            lambda _: review_nudge.record_prompt(vault, "codex", session_id, project_id),
            range(60),
        ))

    assert all(results)
    state = read_json(RuntimeConfig(vault).root / "review-nudge.json")
    assert len(state["counters"]) == 1
    assert state["counters"][0]["prompt_count"] == 60


def test_expired_counter_is_restarted_not_carried_forward(runtime_fixture):
    vault, project_id = runtime_fixture
    assert review_nudge.record_prompt(vault, "claude", "old-session", project_id)
    path = RuntimeConfig(vault).root / "review-nudge.json"
    state = read_json(path)
    stale = datetime.now(timezone.utc) - timedelta(days=8)
    state["counters"][0]["last_seen_at"] = stale.isoformat().replace("+00:00", "Z")
    state["counters"][0]["expires_at"] = (stale + timedelta(days=7)).isoformat().replace("+00:00", "Z")
    write_json(path, state)

    assert review_nudge.record_prompt(vault, "claude", "old-session", project_id)
    restarted = read_json(path)["counters"]
    assert len(restarted) == 1
    assert restarted[0]["prompt_count"] == 1


def test_corrupt_ledger_fails_closed_without_overwrite(runtime_fixture):
    vault, project_id = runtime_fixture
    path = RuntimeConfig(vault).root / "review-nudge.json"
    path.write_text('{"schema_version": 999}', encoding="utf-8")

    assert not review_nudge.record_prompt(vault, "claude", "session-corrupt", project_id)
    assert path.read_text(encoding="utf-8") == '{"schema_version": 999}'


def test_launcher_counts_before_service_readiness_without_persisting_prompt(runtime_fixture, monkeypatch):
    vault, project_id = runtime_fixture
    monkeypatch.setattr("brain_eleven.runtime.launcher.ensure_service", lambda *_args, **_kwargs: False)

    result = hook(vault, "claude", "UserPromptSubmit", {
        "cwd": str(vault),
        "session_id": "service-degraded-session",
        "turn_id": "turn-1",
        "prompt": "UNIQUE_PROMPT_SENTINEL_DO_NOT_SAVE",
    })

    assert result.get("systemMessage")
    state_path = RuntimeConfig(vault).root / "review-nudge.json"
    state_text = state_path.read_text(encoding="utf-8")
    state = read_json(state_path)
    assert state["counters"][0]["project_id"] == project_id
    assert state["counters"][0]["prompt_count"] == 1
    assert "UNIQUE_PROMPT_SENTINEL_DO_NOT_SAVE" not in state_text
    assert "service-degraded-session" not in state_text
