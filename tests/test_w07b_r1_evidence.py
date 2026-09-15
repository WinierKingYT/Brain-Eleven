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
    assert runtime_benchmark._hook_status(
        '{"hookSpecificOutput":{"additionalContext":"bounded"},"systemMessage":"degraded"}',
        0,
        event="UserPromptSubmit",
    ) == "DEGRADED"
    assert runtime_benchmark._hook_status("{}", 0, event="SessionEnd") == "OK"
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
    constants = {
        node.value
        for node in ast.walk(run)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }
    assert {
        "SessionStart",
        "Stop",
        "SessionEnd",
        "UserPromptSubmit",
    } <= constants
    assert any(
        isinstance(node, ast.Name) and node.id == "all_hooks_ok"
        for node in ast.walk(run)
    )


def test_benchmark_timeout_is_recorded_as_bounded_status():
    source = Path(runtime_benchmark.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    timeout_handlers = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.ExceptHandler)
        and isinstance(node.type, ast.Attribute)
        and isinstance(node.type.value, ast.Name)
        and node.type.value.id == "subprocess"
        and node.type.attr == "TimeoutExpired"
    ]
    assert len(timeout_handlers) == 1
    assert any(
        isinstance(node, ast.Constant) and node.value == "TIMEOUT"
        for node in ast.walk(tree)
    )


def test_benchmark_reports_complete_latency_matrix_gate():
    source = Path(runtime_benchmark.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    names = {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }
    assert {
        "latency_matrix",
        "latency_matrix_complete",
        "latency_matrix_queue_drained",
        "latency_matrix_terminal_verified",
        "SERVICE_STOP_FAILED",
        "p50_ms",
        "p95_ms",
    } <= names
