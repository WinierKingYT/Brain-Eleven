"""Focused tests for the W-07B evidence-harness boundary."""

import ast
from pathlib import Path

from evals import runtime_benchmark


def test_hook_status_maps_launcher_results_without_retaining_content():
    assert runtime_benchmark._hook_status("{}", 0, event="Stop") == "OK"
    assert runtime_benchmark._hook_status(
        '{"systemMessage":"private prompt must not be persisted"}', 0, event="Stop"
    ) == "DEGRADED"
    assert runtime_benchmark._hook_status(
        '{"hookSpecificOutput":{"additionalContext":"private context"}}',
        0,
        event="UserPromptSubmit",
    ) == "OK"
    assert runtime_benchmark._hook_status("not-json", 0, event="Stop") == "INVALID_OUTPUT"
    assert runtime_benchmark._hook_status("{}", 1, event="Stop") == "NONZERO_EXIT"


def test_synthetic_benchmark_binds_both_clients_to_disposable_transcript_roots():
    source = Path(runtime_benchmark.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    names = {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }
    assert "transcript_roots" in names
    assert "claude" in names
    assert "codex" in names


def test_benchmark_failure_is_visible_instead_of_raising_on_hook_degradation():
    source = Path(runtime_benchmark.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    run = next(
        node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "run"
    )
    calls = [
        node
        for node in ast.walk(run)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "_hook_status"
    ]
    assert {
        keyword.value.value
        for call in calls
        for keyword in call.keywords
        if keyword.arg == "event" and isinstance(keyword.value, ast.Constant)
    } == {
        "Stop",
        "UserPromptSubmit",
    }
    assert any(
        isinstance(node, ast.Name) and node.id == "all_hooks_ok"
        for node in ast.walk(run)
    )
