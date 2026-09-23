"""V1 SessionStart rendering and at-most-once review-nudge delivery."""

from brain_eleven.runtime import review as review_module
from brain_eleven.runtime.context import compile_bootstrap
from brain_eleven.runtime.review import ReviewStore
from brain_eleven.runtime import review_nudge
from brain_eleven.runtime.storage import RuntimeConfig, read_json, write_json
from tests.test_pre13_runtime import runtime as runtime_fixture


def _add_pending(store, project_id, candidate_id, content, evidence):
    return store.add({
        "candidate_id": candidate_id,
        "candidate_type": "NEW_MEMORY",
        "project_id": project_id,
        "scope": "project",
        "memory_type": "decision",
        "commitment": "COMMITTED",
        "confidence": 0.8,
        "evidence_refs": [evidence],
        "content": content,
    }, "HUMAN_APPROVAL_REQUIRED", {
        "client": "claude", "session_hash": "session_hash", "evidence_id": evidence, "role": "user",
    })


def _prepare_marker(vault, project_id, session_id):
    for _ in range(5):
        assert review_nudge.record_prompt(vault, "claude", session_id, project_id)
    assert review_nudge.finalize_session(vault, "claude", session_id)


def _markers(vault):
    return read_json(RuntimeConfig(vault).root / "review-nudge.json")["markers"]


def test_visible_b2_group_renders_one_v1_line_and_consumes_marker_once(runtime_fixture):
    vault, project_id = runtime_fixture
    store = ReviewStore(vault)
    private_text = "PRIVATE_REVIEW_PROPOSAL_MUST_NOT_REACH_SESSION_START"
    _add_pending(store, project_id, "proposal-a", private_text, "evidence-a")
    _add_pending(store, project_id, "proposal-b", private_text, "evidence-b")
    _prepare_marker(vault, project_id, "ended-session-one")
    RuntimeConfig(vault).set_mode("SHADOW")

    first = compile_bootstrap(vault, vault, session="new-session")
    assert first["status"] == "SUCCESS"
    assert first["delivered"] is True
    assert first["context"].count("1 review candidate group is waiting for review.") == 1
    assert private_text not in first["context"]
    assert _markers(vault) == []

    second = compile_bootstrap(vault, vault, session="duplicate-session-start")
    assert "review candidate group" not in second["context"]


def test_multiple_session_markers_coalesce_into_one_line(runtime_fixture):
    vault, project_id = runtime_fixture
    _add_pending(ReviewStore(vault), project_id, "proposal-one", "First proposal", "ev-one")
    _add_pending(ReviewStore(vault), project_id, "proposal-two", "Second proposal", "ev-two")
    _prepare_marker(vault, project_id, "ended-session-one")
    _prepare_marker(vault, project_id, "ended-session-two")

    result = compile_bootstrap(vault, vault, session="new-session")

    assert result["context"].count("review candidate groups are waiting for review.") == 1
    assert _markers(vault) == []


def test_zero_pending_groups_consumes_marker_without_line(runtime_fixture):
    vault, project_id = runtime_fixture
    _prepare_marker(vault, project_id, "no-candidates-session")

    result = compile_bootstrap(vault, vault, session="new-session")

    assert "review candidate" not in result["context"]
    assert _markers(vault) == []


def test_unknown_legacy_index_retains_marker_and_never_reads_candidate_body(runtime_fixture, monkeypatch):
    vault, project_id = runtime_fixture
    store = ReviewStore(vault)
    _add_pending(store, project_id, "legacy-proposal", "Legacy candidate secret text", "legacy-evidence")
    store.pending_index_path.unlink()
    _prepare_marker(vault, project_id, "legacy-index-session")
    original_read_json = review_module.read_json

    def reject_candidate_read(path, default=None):
        assert not path.name.startswith("rev_")
        return original_read_json(path, default)

    monkeypatch.setattr(review_module, "read_json", reject_candidate_read)
    monkeypatch.setattr(ReviewStore, "list", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("list called")))
    monkeypatch.setattr(ReviewStore, "expire", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("expire called")))

    result = compile_bootstrap(vault, vault, session="new-session")

    assert "review candidate" not in result["context"]
    assert len(_markers(vault)) == 1
    assert not store.pending_index_path.exists()


def test_budget_overflow_retains_marker(runtime_fixture):
    vault, project_id = runtime_fixture
    _add_pending(ReviewStore(vault), project_id, "budget-proposal", "Pending text", "budget-evidence")
    _prepare_marker(vault, project_id, "budget-session")

    result = compile_bootstrap(vault, vault, budget=105, session="new-session")

    assert result["status"] == "SUCCESS"
    assert result["estimated_tokens"] <= 105
    assert "review candidate" not in result["context"]
    assert len(_markers(vault)) == 1


def test_absent_marker_output_remains_byte_for_byte_v1(runtime_fixture, monkeypatch):
    vault, _ = runtime_fixture
    import brain_eleven.runtime.review_nudge as nudge_module

    expected = compile_bootstrap(vault, vault, session="baseline-session")
    monkeypatch.setattr(nudge_module, "project_markers", lambda *_args, **_kwargs: [])
    actual = compile_bootstrap(vault, vault, session="baseline-session")

    assert actual == expected
    assert "review candidate" not in actual["context"]


def test_failed_marker_consumption_omits_line_and_preserves_marker(runtime_fixture, monkeypatch):
    vault, project_id = runtime_fixture
    _add_pending(ReviewStore(vault), project_id, "racing-proposal", "Pending text", "racing-evidence")
    _prepare_marker(vault, project_id, "racing-session")
    monkeypatch.setattr(review_nudge, "consume_project_markers", lambda *_args, **_kwargs: False)

    result = compile_bootstrap(vault, vault, session="new-session")

    assert "review candidate" not in result["context"]
    assert len(_markers(vault)) == 1


def test_off_mode_suppresses_delivery_and_preserves_marker(runtime_fixture):
    vault, project_id = runtime_fixture
    _add_pending(ReviewStore(vault), project_id, "off-proposal", "Pending text", "off-evidence")
    _prepare_marker(vault, project_id, "off-session-start")
    RuntimeConfig(vault).set_mode("OFF")

    result = compile_bootstrap(vault, vault, session="new-session")

    assert result["status"] == "OFF"
    assert "review candidate" not in result["context"]
    assert len(_markers(vault)) == 1


def test_failed_final_scope_recheck_retains_marker(runtime_fixture, monkeypatch):
    from brain_eleven._legacy import load_legacy_module

    vault, project_id = runtime_fixture
    _add_pending(ReviewStore(vault), project_id, "scope-proposal", "Pending text", "scope-evidence")
    _prepare_marker(vault, project_id, "scope-session-start")
    compiler = load_legacy_module(
        "brain_eleven_legacy_context_compiler", "context-compiler.py"
    ).ContextCompiler
    original = compiler._generate_context_block

    def turn_off_after_render(self, *args):
        output = original(self, *args)
        RuntimeConfig(vault).set_mode("OFF")
        return output

    monkeypatch.setattr(compiler, "_generate_context_block", turn_off_after_render)

    result = compile_bootstrap(vault, vault, session="new-session")

    assert result["status"] == "SCOPE_DISABLED"
    assert "review candidate" not in result["context"]
    assert len(_markers(vault)) == 1


def test_failed_final_revision_recheck_retains_marker(runtime_fixture, monkeypatch):
    from brain_eleven._legacy import load_legacy_module

    vault, project_id = runtime_fixture
    _add_pending(ReviewStore(vault), project_id, "revision-proposal", "Pending text", "revision-evidence")
    _prepare_marker(vault, project_id, "revision-session-start")
    compiler = load_legacy_module(
        "brain_eleven_legacy_context_compiler", "context-compiler.py"
    ).ContextCompiler
    original = compiler._ensure_output_is_current
    calls = 0

    def stale_on_final_check(self, lineage):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("source changed before nudge delivery")
        return original(self, lineage)

    monkeypatch.setattr(compiler, "_ensure_output_is_current", stale_on_final_check)

    result = compile_bootstrap(vault, vault, session="new-session")

    assert calls == 2
    assert "review candidate" not in result["context"]
    assert len(_markers(vault)) == 1


def test_corrupt_marker_ledger_fails_open_without_nudge(runtime_fixture):
    vault, project_id = runtime_fixture
    _add_pending(ReviewStore(vault), project_id, "corrupt-ledger-proposal", "Pending text", "bad-state-evidence")
    _prepare_marker(vault, project_id, "corrupt-ledger-session")
    path = RuntimeConfig(vault).root / "review-nudge.json"
    path.write_text('{"schema_version": 999}', encoding="utf-8")

    result = compile_bootstrap(vault, vault, session="new-session")

    assert result["status"] == "SUCCESS"
    assert "review candidate" not in result["context"]
    assert path.read_text(encoding="utf-8") == '{"schema_version": 999}'


def test_subthreshold_marker_fails_closed_without_nudge(runtime_fixture):
    vault, project_id = runtime_fixture
    _add_pending(ReviewStore(vault), project_id, "subthreshold-proposal", "Pending text", "subthreshold-evidence")
    _prepare_marker(vault, project_id, "subthreshold-session")
    path = RuntimeConfig(vault).root / "review-nudge.json"
    state = read_json(path)
    state["markers"][0]["prompt_count"] = review_nudge.MIN_PROMPTS_FOR_NUDGE - 1
    write_json(path, state)

    result = compile_bootstrap(vault, vault, session="new-session")

    assert result["status"] == "SUCCESS"
    assert "review candidate" not in result["context"]
    assert read_json(path)["markers"][0]["prompt_count"] == 4
