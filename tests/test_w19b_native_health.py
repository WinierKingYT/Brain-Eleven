"""W-19B native hook health and doctor truthfulness tests."""

import io
import json
import sys

from brain_eleven.memory import MemoryStore
from brain_eleven.projects.registry import ProjectRegistry
from brain_eleven.runtime import install, launcher
from brain_eleven.runtime.storage import RuntimeConfig, read_json, write_json
from brain_eleven.state import StateStore


def _vault(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    project = ProjectRegistry(vault).register(vault, proactive_capture=True)
    StateStore(vault).init_project(project["project_id"],
                                   source={"type": "user", "reference": "w19b"})
    return vault


def _run_main(vault, monkeypatch, result):
    monkeypatch.setattr(launcher, "hook", lambda *args, **kwargs: result)
    monkeypatch.setattr(sys, "stdin", type("Input", (), {
        "buffer": io.BytesIO(json.dumps({"cwd": str(vault), "session_id": "w19b"}).encode())
    })())
    assert launcher.main(["--vault", str(vault), "--client", "codex",
                          "--event", "SessionStart"]) == 0
    return read_json(RuntimeConfig(vault).root / "last-hook.json")


def test_warning_return_persists_degraded_native_status(tmp_path, monkeypatch, capsys):
    vault = _vault(tmp_path)

    record = _run_main(vault, monkeypatch, {"systemMessage": "bounded warning"})

    assert record["status"] == "DEGRADED"
    output = json.loads(capsys.readouterr().out)
    assert output == {"systemMessage": "bounded warning"}


def test_warning_free_return_persists_ok_status(tmp_path, monkeypatch, capsys):
    vault = _vault(tmp_path)

    record = _run_main(vault, monkeypatch, {})

    assert record["status"] == "OK"
    assert json.loads(capsys.readouterr().out) == {}


def test_exception_path_remains_degraded_and_content_free(tmp_path, monkeypatch, capsys):
    vault = _vault(tmp_path)
    monkeypatch.setattr(launcher, "hook", lambda *args, **kwargs: (_ for _ in ()).throw(
        RuntimeError("private prompt and exception")))
    monkeypatch.setattr(sys, "stdin", type("Input", (), {
        "buffer": io.BytesIO(json.dumps({"cwd": str(vault), "session_id": "w19b"}).encode())
    })())

    assert launcher.main(["--vault", str(vault), "--client", "codex",
                          "--event", "SessionStart"]) == 0
    record = read_json(RuntimeConfig(vault).root / "last-hook.json")

    assert record["status"] == "DEGRADED"
    assert "private prompt" not in capsys.readouterr().out


def test_doctor_surfaces_native_degraded_status(tmp_path, monkeypatch):
    vault = _vault(tmp_path)
    write_json(RuntimeConfig(vault).root / "last-hook.json", {
        "at": "2026-09-15T10:00:00+00:00", "client": "codex",
        "event": "SessionStart", "status": "DEGRADED", "elapsed_ms": 4,
    })
    monkeypatch.setattr(install, "client_paths", lambda home=None: {})

    checks = install.doctor(vault)

    assert checks["last_hook"]["status"] == "DEGRADED"
    assert checks["status"] == "ATTENTION"


def test_doctor_missing_or_corrupt_native_breadcrumb_is_bounded(tmp_path, monkeypatch):
    vault = _vault(tmp_path)
    monkeypatch.setattr(install, "client_paths", lambda home=None: {})
    runtime_root = RuntimeConfig(vault).root

    missing = install.doctor(vault)
    assert missing["last_hook"] == {}
    runtime_root.mkdir(parents=True, exist_ok=True)
    (runtime_root / "last-hook.json").write_text("{broken", encoding="utf-8")
    corrupt = install.doctor(vault)

    assert corrupt["last_hook"] == {}
    assert corrupt["status"] == "READY"


def test_later_success_clears_degraded_diagnostic_without_canonical_change(tmp_path, monkeypatch):
    vault = _vault(tmp_path)
    before_memory = MemoryStore(vault).revision()
    before_state = StateStore(vault).project_revision(
        ProjectRegistry(vault).resolve(vault)["project_id"])
    _run_main(vault, monkeypatch, {"systemMessage": "temporary"})
    assert read_json(RuntimeConfig(vault).root / "last-hook.json")["status"] == "DEGRADED"

    record = _run_main(vault, monkeypatch, {})

    assert record["status"] == "OK"
    assert MemoryStore(vault).revision() == before_memory
    project_id = ProjectRegistry(vault).resolve(vault)["project_id"]
    assert StateStore(vault).project_revision(project_id) == before_state
