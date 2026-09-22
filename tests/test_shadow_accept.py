"""Human-approved accept in SHADOW, behind an explicit flag that defaults to off.

The quality gate still governs CANARY and any V2 promotion. This flag only lets a
person accept a reviewed candidate while the runtime stays in SHADOW; it never opens
the automatic worker path and never applies while the runtime is OFF.
"""

import json
import re

import pytest
from fastapi.testclient import TestClient

from brain_eleven.__main__ import main as cli
from brain_eleven.memory import MemoryStore
from brain_eleven.projects.registry import ProjectRegistry
from brain_eleven.runtime.context import compile_context
from brain_eleven.runtime.migration import migrate
from brain_eleven.runtime.review import ReviewStore
from brain_eleven.runtime.service import create_app, review_action, runtime_status
from brain_eleven.runtime.storage import RuntimeConfig, write_json
from brain_eleven.runtime.worker import Worker, apply_candidate, enqueue
from brain_eleven.state import StateService


def _config(vault, project_id, tmp_path, *, mode, shadow_accept=None):
    config = {
        "schema_version": 1,
        "mode": mode,
        "project_ids": [project_id],
        "local_model": None,
        "b1_human_approval": True,
        "transcript_roots": {"claude": [str(tmp_path)], "codex": [str(tmp_path)]},
    }
    if shadow_accept is not None:
        config["shadow_accept"] = shadow_accept
    write_json(RuntimeConfig(vault).path, config)


def _runtime(tmp_path, *, shadow_accept=None):
    vault = tmp_path / "vault"
    vault.mkdir()
    project = ProjectRegistry(vault).register(vault, proactive_capture=True)
    StateService(vault).init_project(project["project_id"], source={"type": "user", "reference": "shadow-accept"})
    migrate(vault)
    _config(vault, project["project_id"], tmp_path, mode="SHADOW", shadow_accept=shadow_accept)
    return vault, project["project_id"]


def _pending_item(tmp_path, vault):
    """Capture one real transcript in SHADOW so a genuine review item exists."""
    # Mirror brain_eleven.runtime.ownership._project_slug exactly (the real
    # Claude Code CLI's own slug: every non-alphanumeric character becomes
    # "-", one hyphen per character -- W-07B capture-silent-gap).
    slug = re.sub(r"[^A-Za-z0-9]", "-", str(vault.resolve()))
    directory = tmp_path / slug
    directory.mkdir(exist_ok=True)
    path = directory / "shadow-session.jsonl"
    path.write_text(json.dumps({
        "type": "user", "sessionId": "shadow-session",
        "message": {"role": "user", "content": "We decided to use SQLite for the shadow accept path."},
    }) + "\n", encoding="utf-8")
    enqueue(vault, "claude", {"session_id": "shadow-session", "cwd": str(vault), "transcript_path": str(path)})
    assert Worker(vault).once()["review_effect_count"] == 1
    (item,) = [x for x in ReviewStore(vault).list() if x["status"] == "PENDING"]
    return item


def _accept(vault, item):
    return review_action(vault, item["id"], "accept", {"expected_revision": MemoryStore(vault).revision()})


def test_flag_defaults_to_off_and_must_be_boolean(tmp_path):
    vault, project = _runtime(tmp_path)
    assert RuntimeConfig(vault).load()["shadow_accept"] is False

    _config(vault, project, tmp_path, mode="SHADOW", shadow_accept="yes")
    with pytest.raises(ValueError):
        RuntimeConfig(vault).load()


def test_setter_rejects_non_boolean_values(tmp_path):
    vault, _ = _runtime(tmp_path)
    with pytest.raises(ValueError):
        RuntimeConfig(vault).set_shadow_accept("yes")
    assert RuntimeConfig(vault).set_shadow_accept(True)["shadow_accept"] is True


def test_shadow_accept_is_refused_by_default(tmp_path):
    vault, _ = _runtime(tmp_path)
    item = _pending_item(tmp_path, vault)

    with pytest.raises(ValueError):
        _accept(vault, item)

    assert not MemoryStore(vault).load()["validated_memory"]
    assert ReviewStore(vault).list()[0]["status"] == "PENDING"


def test_flagged_shadow_accept_writes_one_canonical_memory_and_reaches_session_start(tmp_path):
    vault, _ = _runtime(tmp_path, shadow_accept=True)
    item = _pending_item(tmp_path, vault)
    assert "SQLite" not in compile_context(vault, vault, "Continue", event="SessionStart")["context"]

    accepted = _accept(vault, item)

    assert accepted["status"] == "ACCEPTED"
    assert len(MemoryStore(vault).load()["validated_memory"]) == 1
    assert RuntimeConfig(vault).load()["mode"] == "SHADOW"               # the mode did not move
    assert _accept(vault, item)["status"] == "ACCEPTED"                   # replay is terminal
    assert len(MemoryStore(vault).load()["validated_memory"]) == 1
    assert "SQLite" in compile_context(vault, vault, "Continue", event="SessionStart")["context"]


def test_flag_never_opens_the_automatic_path(tmp_path):
    vault, _ = _runtime(tmp_path, shadow_accept=True)
    item = _pending_item(tmp_path, vault)

    # No human approval: the same effect the worker would apply on its own.
    outcome = apply_candidate(vault, item["candidate"], op_id="op_auto_shadow")

    assert outcome == {"status": "SCOPE_ERROR"}
    assert not MemoryStore(vault).load()["validated_memory"]


def test_flag_does_not_apply_while_the_runtime_is_off(tmp_path):
    vault, project = _runtime(tmp_path, shadow_accept=True)
    item = _pending_item(tmp_path, vault)
    _config(vault, project, tmp_path, mode="OFF", shadow_accept=True)

    with pytest.raises(ValueError):
        _accept(vault, item)
    assert apply_candidate(vault, item["candidate"], op_id="op_off", approved=True) == {"status": "SCOPE_ERROR"}
    assert not MemoryStore(vault).load()["validated_memory"]


def test_runtime_status_reports_the_flag(tmp_path):
    vault, project = _runtime(tmp_path)
    assert runtime_status(vault)["shadow_accept"] is False
    _config(vault, project, tmp_path, mode="SHADOW", shadow_accept=True)
    assert runtime_status(vault)["shadow_accept"] is True


def test_cli_toggles_the_flag(tmp_path, capsys):
    vault, _ = _runtime(tmp_path)

    assert cli(["--vault", str(vault), "shadow-accept", "ON"]) == 0
    assert RuntimeConfig(vault).load()["shadow_accept"] is True
    assert cli(["--vault", str(vault), "shadow-accept", "OFF"]) == 0
    assert RuntimeConfig(vault).load()["shadow_accept"] is False
    capsys.readouterr()


def test_review_page_enables_accept_from_the_flag(tmp_path):
    vault, _ = _runtime(tmp_path)
    app = create_app(vault, token="shadow-token", background=False)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        script = client.get("/review.js").text
    assert "shadow_accept" in script
