"""Cross-boundary IG04-B3 hook, renderer and failure tests."""

import os
import subprocess
from types import SimpleNamespace
from concurrent.futures import ThreadPoolExecutor

from brain_eleven.runtime import review_nudge
from brain_eleven.runtime.context import compile_bootstrap, compile_context
from brain_eleven.runtime.review import ReviewStore
from brain_eleven.runtime.storage import RuntimeConfig, read_json
from tests.test_ig04b3_session_start_nudge import _add_pending, _markers
from tests.test_pre13_runtime import runtime as runtime_fixture


def test_prompt_stop_session_end_and_v1_session_start_form_one_flow(runtime_fixture, monkeypatch):
    from brain_eleven.runtime import launcher

    vault, project_id = runtime_fixture
    RuntimeConfig(vault).set_mode("SHADOW")
    _add_pending(ReviewStore(vault), project_id, "full-flow-proposal", "Private proposal body", "full-flow-evidence")
    session_id = "full-native-flow-session"
    monkeypatch.setattr(launcher, "ensure_service", lambda *_args, **_kwargs: True)
    monkeypatch.setattr("brain_eleven.runtime.worker.enqueue", lambda *_args, **_kwargs: {"status": "QUEUED"})

    def service_request(_vault, route, payload, **_kwargs):
        if payload["event"] == "SessionStart":
            return compile_context(
                vault, payload["project_root"], payload["request"],
                client=payload["client"], session=payload["session"], turn=payload["turn"],
                event="SessionStart",
            )
        return {
            "status": "SUCCESS", "context": "safe V1 context", "selected_ids": [],
            "provider": "V1", "delivery_approved": True, "delivered": True,
        }

    monkeypatch.setattr(launcher, "request_service", service_request)
    for index in range(5):
        submitted = launcher.hook(vault, "claude", "UserPromptSubmit", {
            "cwd": str(vault), "session_id": session_id, "turn_id": f"turn-{index}",
            "prompt": f"PRIVATE_PROMPT_{index}",
        })
        assert isinstance(submitted, tuple)

    state_path = RuntimeConfig(vault).root / "review-nudge.json"
    counter = read_json(state_path)["counters"][0]
    assert counter["prompt_count"] == 5
    before_stop = read_json(state_path)
    assert launcher.hook(vault, "claude", "Stop", {
        "cwd": str(vault), "session_id": session_id, "transcript_path": "unused",
    }) == {}
    assert read_json(state_path) == before_stop

    assert launcher.hook(vault, "claude", "SessionEnd", {
        "cwd": str(vault), "session_id": session_id,
    }) == {}
    assert len(_markers(vault)) == 1

    started = launcher.hook(vault, "claude", "SessionStart", {
        "cwd": str(vault), "session_id": "new-session-start",
    })
    output = started[0]
    assert "hookSpecificOutput" in output
    rendered = output["hookSpecificOutput"]["additionalContext"]
    assert "1 review candidate group is waiting for review." in rendered
    assert "Private proposal body" not in rendered
    assert all(f"PRIVATE_PROMPT_{index}" not in state_path.read_text(encoding="utf-8") for index in range(5))
    assert _markers(vault) == []


def test_concurrent_session_starts_emit_at_most_one_nudge(runtime_fixture):
    vault, project_id = runtime_fixture
    _add_pending(ReviewStore(vault), project_id, "race-proposal", "Private proposal body", "race-evidence")
    for _ in range(5):
        assert review_nudge.record_prompt(vault, "codex", "race-ended-session", project_id)
    assert review_nudge.finalize_session(vault, "codex", "race-ended-session")

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(
            lambda index: compile_bootstrap(vault, vault, session=f"race-start-{index}"),
            range(2),
        ))

    emitted = ["review candidate group is waiting for review." in result["context"] for result in results]
    assert sum(emitted) == 1
    assert _markers(vault) == []


def test_marker_lock_failure_is_silent_and_preserves_marker(runtime_fixture, monkeypatch):
    vault, project_id = runtime_fixture
    _add_pending(ReviewStore(vault), project_id, "lock-failure-proposal", "Pending text", "lock-evidence")
    for _ in range(5):
        review_nudge.record_prompt(vault, "claude", "lock-failure-session", project_id)
    review_nudge.finalize_session(vault, "claude", "lock-failure-session")

    def fail_lock(*_args, **_kwargs):
        raise TimeoutError("simulated marker lock timeout")

    monkeypatch.setattr(review_nudge, "runtime_file_lock", fail_lock)
    result = compile_bootstrap(vault, vault, session="new-session")

    assert result["status"] == "SUCCESS"
    assert "review candidate" not in result["context"]
    assert len(_markers(vault)) == 1


def test_background_service_launcher_requests_windowless_creationflag(runtime_fixture, monkeypatch):
    from brain_eleven.runtime import launcher

    vault, _ = runtime_fixture
    calls = []
    monkeypatch.setattr(launcher, "os", SimpleNamespace(name="nt", kill=os.kill))
    monkeypatch.setattr(
        subprocess, "CREATE_NO_WINDOW", getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000), raising=False,
    )
    monkeypatch.setattr(
        subprocess, "DETACHED_PROCESS", getattr(subprocess, "DETACHED_PROCESS", 0x00000008), raising=False,
    )
    monkeypatch.setattr(launcher, "request_service", lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("offline")))

    class Process:
        pid = 42

    monkeypatch.setattr(launcher.subprocess, "Popen", lambda *args, **kwargs: calls.append(kwargs) or Process())

    assert launcher.ensure_service(vault) is False
    assert len(calls) == 1
    assert calls[0]["creationflags"] & subprocess.CREATE_NO_WINDOW
    assert not calls[0]["creationflags"] & getattr(subprocess, "DETACHED_PROCESS", 0)
