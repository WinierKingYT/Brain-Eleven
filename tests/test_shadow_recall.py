"""Owner opt-in (2026-09-27): SHADOW may deliver V1 per-prompt context; V2 never."""

import pytest

from brain_eleven.__main__ import main
from brain_eleven.runtime.context import compile_context
from brain_eleven.runtime.storage import RuntimeConfig, identity, write_json
from brain_eleven.runtime.worker import apply_candidate
from tests.test_pre13_runtime import candidate, runtime  # noqa: F401


def test_shadow_recall_is_off_by_default_and_delivers_v1_only_when_on(runtime):
    vault, project = runtime
    apply_candidate(vault, candidate(project), op_id=identity("op_", "shadow-recall"))
    RuntimeConfig(vault).set_mode("SHADOW")
    assert RuntimeConfig(vault).load()["shadow_recall"] is False

    off = compile_context(vault, vault, "Continue the database work")
    assert (off["context"], off["delivered"]) == ("", False)

    main(["--vault", str(vault), "shadow-recall", "ON"])
    on = compile_context(vault, vault, "Continue the database work")
    assert on["provider"] == "V1" and on["delivery_approved"] is True and on["delivered"] is True
    assert "SQLite" in on["context"]
    assert RuntimeConfig(vault).load()["mode"] == "SHADOW"

    RuntimeConfig(vault).set_shadow_recall(False)
    assert compile_context(vault, vault, "Continue the database work")["delivered"] is False


def test_shadow_recall_never_delivers_a_non_v1_provider(runtime, monkeypatch):
    vault, project = runtime
    apply_candidate(vault, candidate(project), op_id=identity("op_", "shadow-recall-v2"))
    RuntimeConfig(vault).set_mode("SHADOW")
    RuntimeConfig(vault).set_shadow_recall(True)
    import brain_eleven.runtime.context as context
    monkeypatch.setattr(context, "compile_task_v1", lambda *a, **k: {
        "status": "SUCCESS", "context": "V2_SENTINEL", "selected_ids": ["x"], "provider": "V2"})
    result = compile_context(vault, vault, "Continue the database work")
    assert (result["context"], result["delivered"]) == ("", False)


def test_invalid_shadow_recall_value_fails_closed(runtime):
    vault, _ = runtime
    config = RuntimeConfig(vault).load()
    config["shadow_recall"] = "yes"
    config.pop("retrieval_mode_telemetry", None)
    write_json(RuntimeConfig(vault).path, config)
    with pytest.raises(ValueError):
        RuntimeConfig(vault).load()
