"""Focused tests for the W-07B evidence-harness boundary."""

import ast
import http.client
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


def test_service_stop_bounds_http_protocol_errors(monkeypatch, tmp_path):
    def raise_protocol_error(*_args, **_kwargs):
        raise http.client.HTTPException("synthetic protocol failure")

    monkeypatch.setattr(runtime_benchmark, "request_service", raise_protocol_error)
    assert runtime_benchmark._stop_service(tmp_path, object(), timeout=0.01) is True


def test_queue_poll_bounds_protocol_and_schema_errors(monkeypatch, tmp_path):
    responses = [
        http.client.HTTPException("synthetic protocol failure"),
        {"queue": []},
        {"queue": {"queued": 0, "processing": 0}},
    ]

    def next_response(*_args, **_kwargs):
        value = responses.pop(0)
        if isinstance(value, Exception):
            raise value
        return value

    monkeypatch.setattr(runtime_benchmark, "request_service", next_response)
    assert runtime_benchmark._wait_for_queue_drain(tmp_path, timeout=0.5) is True
