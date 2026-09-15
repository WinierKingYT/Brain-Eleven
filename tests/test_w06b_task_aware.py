"""Focused W-06B runtime gate, parity, and bounded-output evidence."""

import json

from tests.test_pre13_runtime import candidate, runtime
from brain_eleven.runtime.context import compile_context
from brain_eleven.runtime.storage import RuntimeConfig, identity, read_json, write_json
from brain_eleven.runtime.worker import apply_candidate
from brain_eleven.runtime.task_aware import select
from brain_eleven.memory import MemoryStore


def _set_retrieval_mode(vault, mode):
    value = RuntimeConfig(vault).load()
    value["retrieval_mode"] = mode
    write_json(RuntimeConfig(vault).path, value)


def test_user_prompt_task_aware_path_is_bounded_and_session_start_stays_v1(runtime):
    vault, project = runtime
    apply_candidate(vault, candidate(project), op_id=identity("op_", "w06b"))
    _set_retrieval_mode(vault, "W06B_TASK_AWARE")

    prompt = "Debug the database persistence decision and continue the SQLite work"
    result = compile_context(vault, vault, prompt, event="UserPromptSubmit")
    assert result["provider"] == "W06B_TASK_AWARE"
    assert result["status"] in {"SUCCESS", "EMPTY", "DEGRADED", "UNAVAILABLE"}
    assert len(result.get("selected_ids", [])) <= 5
    assert result.get("estimated_tokens", 0) <= 1024
    assert len(result.get("context", "").encode("utf-8")) <= 8192

    bootstrap = compile_context(vault, vault, prompt, event="SessionStart")
    assert bootstrap["provider"] == "V1"


def test_task_aware_repeated_selection_is_deterministic_and_prompt_is_not_telemetry(runtime):
    vault, project = runtime
    apply_candidate(vault, candidate(project), op_id=identity("op_", "w06b-repeat"))
    _set_retrieval_mode(vault, "W06B_TASK_AWARE")
    prompt = "Review the SQLite persistence decision"
    first = compile_context(vault, vault, prompt, event="UserPromptSubmit")
    second = compile_context(vault, vault, prompt, event="UserPromptSubmit")
    assert first.get("selected_ids") == second.get("selected_ids")
    telemetry = read_json(RuntimeConfig(vault).root / "last-context.json", {})
    assert prompt not in json.dumps(telemetry, ensure_ascii=False)


def test_invalid_gate_fails_closed_and_rollback_restores_v1(runtime):
    vault, project = runtime
    apply_candidate(vault, candidate(project), op_id=identity("op_", "w06b-gate"))
    _set_retrieval_mode(vault, "UNKNOWN_MODE")
    loaded = RuntimeConfig(vault).load()
    assert loaded["retrieval_mode"] == "V1_LEGACY"
    assert loaded["retrieval_mode_telemetry"] == "RETRIEVAL_MODE_INVALID"
    invalid_result = compile_context(vault, vault, "Continue the database work", event="UserPromptSubmit")
    assert invalid_result.get("provider") != "W06B_TASK_AWARE"

    _set_retrieval_mode(vault, "W06B_TASK_AWARE")
    assert compile_context(vault, vault, "Continue the database work", event="UserPromptSubmit")["provider"] == "W06B_TASK_AWARE"
    _set_retrieval_mode(vault, "V1_LEGACY")
    rollback = compile_context(vault, vault, "Continue the database work", event="UserPromptSubmit")
    assert rollback.get("provider") == "V1"


def test_non_string_retrieval_modes_fail_closed(runtime):
    vault, _ = runtime
    for invalid in (None, [], {}, 3):
        value = RuntimeConfig(vault).load()
        value["retrieval_mode"] = invalid
        write_json(RuntimeConfig(vault).path, value)
        loaded = RuntimeConfig(vault).load()
        assert loaded["retrieval_mode"] == "V1_LEGACY"
        assert loaded["retrieval_mode_telemetry"] == "RETRIEVAL_MODE_INVALID"


def test_no_need_uses_legacy_selection_with_bounded_task_status(runtime, monkeypatch):
    vault, _ = runtime
    _set_retrieval_mode(vault, "W06B_TASK_AWARE")
    import brain_eleven.runtime.context as context_module
    monkeypatch.setattr(
        context_module,
        "compile_task_w06b",
        lambda *args, **kwargs: {
            "status": "NO_NEED",
            "task_need": {"status": "NO_NEED", "error_code": None},
            "context": "",
            "selected_ids": [],
            "provider": "V1",
        },
    )
    monkeypatch.setattr(
        context_module,
        "compile_task",
        lambda *args, **kwargs: {
            "status": "SUCCESS",
            "context": "legacy",
            "selected_ids": ["legacy-id"],
            "provider": "V1",
        },
    )
    result = compile_context(vault, vault, "hello", event="UserPromptSubmit")
    assert result.get("task_need_status") == "NO_NEED"
    assert result.get("provider") == "V1"
    assert result.get("context") == "legacy"


def test_non_user_prompt_event_keeps_legacy_provider(runtime):
    vault, project = runtime
    _set_retrieval_mode(vault, "W06B_TASK_AWARE")
    result = compile_context(vault, vault, "Implement the database change", event="OtherEvent")
    assert result.get("provider") != "W06B_TASK_AWARE"


def test_b1_approval_filter_excludes_unapproved_records(runtime):
    vault, project = runtime
    apply_candidate(vault, candidate(project), op_id=identity("op_", "approval"))
    store = MemoryStore(vault)
    document = store.load()
    document["validated_memory"][0]["is_approved"] = False
    store.replace(document, expected_revision=document["revision"])
    _set_retrieval_mode(vault, "W06B_TASK_AWARE")
    value = RuntimeConfig(vault).load()
    value["b1_human_approval"] = True
    write_json(RuntimeConfig(vault).path, value)
    result = compile_context(vault, vault, "Review the SQLite decision", event="UserPromptSubmit")
    assert result.get("selected_ids", []) == []


def test_equal_score_tie_is_independent_of_input_order():
    class Compiler:
        def _rank_memories(self, limit=40):
            return list(self.records)
        def _resolve_current_state(self):
            return object()
        def _generate_context_block(self, records, *_):
            return "\n".join(x["content"] for x in records)
    class Task:
        task_id = "tsk_test"
        raw_request = "Review alpha beta"
        entities = ()
        context_needs = ()
        continuation_of = None
        project = type("P", (), {"project_id": "p"})()
        intent = type("I", (), {"value": "REVIEW"})()
    records = [
        {"id": "b", "project_id": "p", "content": "alpha beta", "ranking_score": 1, "type": "decision"},
        {"id": "a", "project_id": "p", "content": "alpha beta", "ranking_score": 1, "type": "decision"},
    ]
    first = Compiler(); first.records = records
    second = Compiler(); second.records = list(reversed(records))
    assert select(first, Task()) ["selected_ids"] == select(second, Task())["selected_ids"]


def test_canonical_global_records_are_selected_without_cross_project_leakage():
    class Compiler:
        def _rank_memories(self, limit=40):
            return [
                {
                    "memory_id": "global-empty",
                    "scope": "global",
                    "project_id": "",
                    "content": "global persistence policy",
                    "ranking_score": 3,
                    "type": "lesson",
                },
                {
                    "memory_id": "global-legacy",
                    "content": "legacy global persistence policy",
                    "ranking_score": 2,
                    "type": "lesson",
                },
                {
                    "memory_id": "foreign-project",
                    "scope": "project",
                    "project_id": "project-b",
                    "content": "foreign project persistence policy",
                    "ranking_score": 4,
                    "type": "decision",
                },
            ]

        def _resolve_current_state(self):
            return object()

        def _generate_context_block(self, records, *_):
            return "\n".join(item["content"] for item in records)

    class Task:
        task_id = "tsk_global_scope"
        raw_request = "Review the global persistence policy"
        entities = ()
        context_needs = ()
        continuation_of = None
        project = type("Project", (), {"project_id": "project-a"})()
        intent = type("Intent", (), {"value": "REVIEW"})()

    result = select(Compiler(), Task())

    assert result["status"] == "SUCCESS"
    assert {"global-empty", "global-legacy"} <= set(result["selected_ids"])
    assert "foreign-project" not in result["selected_ids"]
