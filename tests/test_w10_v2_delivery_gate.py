"""W-10: V2 shadow output never crosses the native model boundary."""

import json

from brain_eleven.runtime.context import compile_bootstrap, compile_context
from brain_eleven.runtime.storage import RuntimeConfig, read_json, write_json
from brain_eleven.runtime.worker import apply_candidate
from tests.test_pre13_runtime import candidate, runtime


def test_normal_v1_delivery_is_project_scoped_and_ignores_companion(runtime):
    vault, project = runtime
    apply_candidate(vault, candidate(project), op_id="w10-project-scoped")
    (vault / "🔮 Companion").mkdir(exist_ok=True)
    (vault / "🔮 Companion" / "Last Session.md").write_text("W10_COMPANION_SENTINEL", encoding="utf-8")
    (vault / "🔮 Companion" / "Açık Döngüler.md").write_text("W10_OPEN_LOOP_SENTINEL", encoding="utf-8")
    config = RuntimeConfig(vault).load()
    config["mode"] = "CANARY"
    write_json(RuntimeConfig(vault).path, config)

    result = compile_context(vault, vault, "Continue the database work")
    bootstrap = compile_bootstrap(vault, vault)

    assert result["provider"] == "V1"
    assert result["delivery_approved"] is True
    assert result["delivered"] is True
    assert result["context"] == bootstrap["context"]
    assert "W10_COMPANION_SENTINEL" not in result["context"]
    assert "W10_OPEN_LOOP_SENTINEL" not in result["context"]
    telemetry = read_json(RuntimeConfig(vault).root / "last-context.json")
    assert "W10_COMPANION_SENTINEL" not in json.dumps(telemetry, ensure_ascii=False)
    assert "W10_OPEN_LOOP_SENTINEL" not in json.dumps(telemetry, ensure_ascii=False)


def test_shadow_normal_turn_is_empty_and_not_delivered(runtime):
    vault, project = runtime
    apply_candidate(vault, candidate(project), op_id="w10-shadow")
    RuntimeConfig(vault).set_mode("SHADOW")

    result = compile_context(vault, vault, "Continue the database work")

    assert result["provider"] == "V1"
    assert result["context"] == ""
    assert result["selected_ids"] == []
    assert result["delivery_approved"] is False
    assert result["delivered"] is False


def test_normal_v1_does_not_invoke_v2_renderer(runtime, monkeypatch):
    vault, project = runtime
    apply_candidate(vault, candidate(project), op_id="w10-no-v2")
    config = RuntimeConfig(vault).load()
    config["mode"] = "CANARY"
    write_json(RuntimeConfig(vault).path, config)

    import brain_eleven.runtime.context as context_module

    def forbidden(*args, **kwargs):
        raise AssertionError("V2 renderer must not run on the model-facing V1 path")

    monkeypatch.setattr(context_module.ContextCompilerV2, "compile", forbidden)
    result = compile_context(vault, vault, "Continue the database work")

    assert result["provider"] == "V1"
    assert result["delivered"] is True


def test_launcher_requires_explicit_current_delivery_fields(runtime, monkeypatch):
    vault, _ = runtime
    from brain_eleven.runtime import launcher

    monkeypatch.setattr(launcher, "ensure_service", lambda *args, **kwargs: True)
    payload = {"cwd": str(vault), "session_id": "w10-gate", "turn_id": "1", "prompt": "Continue"}

    monkeypatch.setattr(launcher, "request_service", lambda *args, **kwargs: {
        "status": "SUCCESS", "context": "V2_SENTINEL", "delivered": True,
        "delivery_approved": True, "provider": "V2",
    })
    output, _, _ = launcher.hook(vault, "codex", "UserPromptSubmit", payload)
    assert "hookSpecificOutput" not in output

    payload["turn_id"] = "2"
    monkeypatch.setattr(launcher, "request_service", lambda *args, **kwargs: {
        "status": "SUCCESS", "context": "V1 context", "delivered": True,
        "delivery_approved": False, "provider": "V1",
    })
    output, _, _ = launcher.hook(vault, "codex", "UserPromptSubmit", payload)
    assert "hookSpecificOutput" not in output

    payload["turn_id"] = "3"
    monkeypatch.setattr(launcher, "request_service", lambda *args, **kwargs: {
        "status": "SUCCESS", "context": "V1 context", "delivered": True,
        "delivery_approved": True, "provider": "V1",
    })
    output, _, _ = launcher.hook(vault, "codex", "UserPromptSubmit", payload)
    assert output["hookSpecificOutput"]["additionalContext"] == "V1 context"


def test_launcher_legacy_mock_compatibility_is_bounded(runtime, monkeypatch):
    vault, _ = runtime
    from brain_eleven.runtime import launcher

    monkeypatch.setattr(launcher, "ensure_service", lambda *args, **kwargs: True)
    monkeypatch.setattr(launcher, "request_service", lambda *args, **kwargs: {
        "status": "SUCCESS", "context": "legacy mock", "delivered": True,
    })
    payload = {"cwd": str(vault), "session_id": "w10-legacy", "turn_id": "1", "prompt": "Continue"}
    output, _, _ = launcher.hook(vault, "codex", "UserPromptSubmit", payload)
    assert output["hookSpecificOutput"]["additionalContext"] == "legacy mock"
