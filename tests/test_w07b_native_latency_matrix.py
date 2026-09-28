"""Pure safety and summary checks for the manual native latency harness."""
from __future__ import annotations

import json
from dataclasses import asdict, fields

import pytest

from evals.w07b import latency_matrix
from evals.w07b import codex_native_smoke, native_smoke
from brain_eleven.runtime.storage import identity


def _complete_observations():
    observations = {}
    for client in latency_matrix.CLIENTS:
        for event in latency_matrix.EVENTS:
            for phase in latency_matrix.PHASES:
                observations[latency_matrix._cell_key(client, event, phase)] = [
                    {"elapsed_ms": value, "status_code": "DELIVERED", "client_status": "OK"}
                    for value in (10, 20, 30, 40, 50)
                ]
    return observations


def test_matrix_summary_covers_both_clients_events_and_phases():
    report = latency_matrix._summarize_matrix(_complete_observations())

    assert report["cell_count"] == 16
    assert report["complete"] is True
    assert report["within_budget"] is True
    assert report["native_runs_completed"] is True
    assert report["acceptance"] is True
    session_start = next(
        cell for cell in report["cells"]
        if cell["client"] == "claude" and cell["event"] == "SessionStart"
        and cell["phase"] == "cold"
    )
    assert session_start["n"] == 5
    assert session_start["p50_ms"] == 30
    assert session_start["p95_ms"] == 50
    assert session_start["budget_ms"] == 2500


def test_matrix_summary_marks_missing_or_over_budget_samples_incomplete():
    observations = _complete_observations()
    observations[latency_matrix._cell_key("codex", "SessionEnd", "cold")] = [
        {"elapsed_ms": 3101, "status_code": "OK", "client_status": "OK"}
    ]

    report = latency_matrix._summarize_matrix(observations)
    session_end = next(
        cell for cell in report["cells"]
        if cell["client"] == "codex" and cell["event"] == "SessionEnd"
        and cell["phase"] == "cold"
    )

    assert report["complete"] is False
    assert report["within_budget"] is False
    assert report["acceptance"] is False
    assert session_end["n"] == 1
    assert session_end["within_budget"] is False


def test_matrix_report_omits_session_ids_prompts_and_paths():
    observations = _complete_observations()
    observations[latency_matrix._cell_key("claude", "SessionStart", "cold")][0].update({
        "session_id": "private-session-id",
        "prompt": "private prompt",
        "transcript_path": "private-local-path",
    })

    serialized = json.dumps(latency_matrix._summarize_matrix(observations))

    assert "private-session-id" not in serialized
    assert "private prompt" not in serialized
    assert "private-local-path" not in serialized
    assert '"session_id"' not in serialized
    assert '"transcript_path"' not in serialized


def test_codex_binding_validator_checks_reviewed_config_without_rewriting(tmp_path, monkeypatch):
    profile = tmp_path / ".codex"
    profile.mkdir()
    vault = tmp_path / "vault"
    runtime = vault / ".brain-eleven" / "runtime"
    runtime.mkdir(parents=True)
    config_path = profile / "hooks.json"
    monkeypatch.setenv("CODEX_HOME", str(profile))

    from brain_eleven.runtime.install import hook_command

    entries = {}
    hooks = {}
    for event in latency_matrix.EVENTS:
        hook = {
            "type": "command",
            "command": hook_command(vault, "codex", event),
            "timeout": 3,
        }
        entries[event] = {"hooks": [hook]}
        hooks[event] = [hook]
    config_path.write_text(json.dumps({"hooks": hooks}), encoding="utf-8")
    manifest = {"clients": {"codex": {"path": str(config_path), "entries": entries}}}
    (runtime / "installation.json").write_text(json.dumps(manifest), encoding="utf-8")
    before = config_path.read_bytes()

    latency_matrix._validate_codex_binding(vault, profile)

    assert config_path.read_bytes() == before

    hooks["SessionStart"][0]["command"] = "other-target"
    config_path.write_text(json.dumps({"hooks": hooks}), encoding="utf-8")
    with pytest.raises(RuntimeError, match="CODEX_HOOK_BINDING_MISMATCH"):
        latency_matrix._validate_codex_binding(vault, profile)


def test_cold_event_polling_stops_service_only_after_predecessor(monkeypatch, tmp_path):
    stopped = []
    monkeypatch.setattr(latency_matrix, "_stop_service", lambda vault: stopped.append(vault) or True)
    poller = latency_matrix._HookPoller(tmp_path, "claude", stop_after="UserPromptSubmit")

    poller._record("SessionStart", "DELIVERED", 12)
    assert stopped == []
    poller._record("UserPromptSubmit", "DELIVERED", 9)

    assert stopped == [tmp_path]
    assert poller.stop_results["UserPromptSubmit"] is True
    assert "session_id" not in poller.samples["SessionStart"]


def test_claude_smoke_receipt_lookup_reports_only_opaque_session_hash(tmp_path):
    session_id = "private-session-value"
    directory = tmp_path / ".brain-eleven" / "runtime" / "deliveries"
    directory.mkdir(parents=True)
    (directory / "delivery_opaque.json").write_text(json.dumps({
        "client": "claude",
        "event": "SessionStart",
        "session_hash": identity("session_", session_id),
        "status": "EMITTED",
        "stage": "DELIVERED",
        "hook_elapsed_ms": 19,
        "context_delivered": True,
    }), encoding="utf-8")

    result = codex_native_smoke._session_receipts(tmp_path, session_id, "claude")

    assert result == {
        "SessionStart": {
            "status": "EMITTED",
            "stage": "DELIVERED",
            "context_delivered": True,
        }
    }
    assert session_id not in json.dumps(result)


def test_claude_smoke_result_has_no_raw_session_identifier_field():
    field_names = {item.name for item in fields(native_smoke.RunResult)}
    assert "session_hash" in field_names
    assert "session_id" not in field_names

    result = native_smoke.RunResult(
        repetition=1,
        exit_code=0,
        elapsed_s=0.1,
        session_hash="sha256:opaque",
        ledger_terminal={},
        hook_receipts={},
        queue_terminal_state="COMMITTED",
        capture_receipt_status="EFFECT_VERIFIED",
        review_effect_id="review_opaque",
        memory_revision_before=1,
        memory_revision_after=1,
        failure_code=None,
    )
    serialized = json.dumps(asdict(result))
    assert "sha256:opaque" in serialized
    assert "session_id" not in serialized
