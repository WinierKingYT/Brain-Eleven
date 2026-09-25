"""The native evidence gate must not accept a successful CLI with missing hooks."""

from evals.w07b.latency_matrix import _gate
from evals.w07b.dogfood import _exercise_failed_retry
from brain_eleven.projects.registry import ProjectRegistry
from brain_eleven.runtime import maintenance_delivery
from brain_eleven.state import StateStore


def _report():
    return {
        "live_files_untouched": True,
        "exit_codes": [0] * 10,
        "cells": {
            "session_start_cold": {"n": 5, "p95": 1800},
            "session_start_warm": {"n": 5, "p95": 600},
            "user_prompt_submit": {"n": 10, "p95": 700},
            "stop": {"n": 10, "p95": 500},
            "session_end": {"n": 10, "p95": 500},
        },
    }


def test_native_latency_gate_requires_every_event_even_when_all_cli_calls_succeed():
    report = _report()
    assert _gate(report, 5, 5)
    report["cells"]["session_start_cold"]["n"] = 4
    assert not _gate(report, 5, 5)
    report["cells"]["session_start_cold"]["n"] = 5
    report["cells"]["user_prompt_submit"]["n"] = 9
    assert not _gate(report, 5, 5)


def test_native_latency_gate_enforces_timeout_and_live_config_integrity():
    report = _report()
    report["cells"]["session_start_cold"]["p95"] = 3000
    assert not _gate(report, 5, 5)
    report["cells"]["session_start_cold"]["p95"] = 1800
    report["live_files_untouched"] = False
    assert not _gate(report, 5, 5)


def test_dogfood_fault_probe_retries_one_real_durable_intent_without_canonical_write(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    project = ProjectRegistry(vault).register(vault, proactive_capture=True)
    StateStore(vault).init_project(project["project_id"], source={"type": "user", "reference": "test"})
    job = {"job_id": "capture-test-1", "event": {"event_type": "SESSION_END", "event_id": "evt-test-1",
                                              "project": {"project_id": project["project_id"]}}}
    maintenance_delivery.enqueue(vault, job, {"status": "PROCESSED", "effect_verified": True})

    assert _exercise_failed_retry(vault) == {
        "native_maintenance_backlog_drained": True,
        "failed_attempt_recorded": True,
        "retry_completed": True,
        "canonical_unchanged": True,
        "staging_empty": True,
    }


def test_dogfood_fault_probe_creates_isolated_intent_if_background_service_drained_queue(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    project = ProjectRegistry(vault).register(vault, proactive_capture=True)
    StateStore(vault).init_project(project["project_id"], source={"type": "user", "reference": "test"})

    assert all(_exercise_failed_retry(vault).values())
