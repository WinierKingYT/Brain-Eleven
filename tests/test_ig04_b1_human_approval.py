"""Focused IG-04 B1 human-approval boundary tests."""

import json

import pytest
from fastapi.testclient import TestClient

from brain_eleven.memory import MemoryStore
from brain_eleven.projects.registry import ProjectRegistry
from brain_eleven.runtime.context import compile_context
from brain_eleven.runtime.review import ReviewStore
from brain_eleven.runtime.service import review_action
from brain_eleven.runtime.service import create_app
from brain_eleven.runtime.storage import RuntimeConfig, identity, write_json
from brain_eleven.runtime.worker import Worker, enqueue
from brain_eleven.runtime.migration import migrate
from brain_eleven.state import StateService


@pytest.fixture
def b1_runtime(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    project = ProjectRegistry(vault).register(vault, proactive_capture=True)
    StateService(vault).init_project(project["project_id"], source={"type": "user", "reference": "ig04-b1"})
    migrate(vault)
    write_json(RuntimeConfig(vault).path, {
        "schema_version": 1,
        "mode": "CANARY",
        "project_ids": [project["project_id"]],
        "local_model": None,
        "b1_human_approval": True,
        "transcript_roots": {"claude": [str(tmp_path)], "codex": [str(tmp_path)]},
    })
    return vault, project["project_id"]


def _transcript(tmp_path, text="We decided to use SQLite for B1 capture."):
    path = tmp_path / "session.jsonl"
    path.write_text(json.dumps({
        "type": "user",
        "message": {"role": "user", "content": text},
    }) + "\n", encoding="utf-8")
    return path


def _candidate(project_id, *, candidate_id="cand-b1", evidence="evd_" + "a" * 32,
               content="We decided to use SQLite for B1 capture."):
    return {
        "candidate_id": candidate_id,
        "candidate_type": "NEW_MEMORY",
        "project_id": project_id,
        "scope": "project",
        "content": content,
        "memory_type": "decision",
        "commitment": "COMMITTED",
        "confidence": 0.97,
        "evidence_refs": [evidence],
    }


def test_b1_capture_requires_review_and_acceptance_is_one_canonical_effect(b1_runtime, tmp_path):
    vault, project = b1_runtime
    path = _transcript(tmp_path)
    enqueue(vault, "claude", {"session_id": "b1-session", "cwd": str(vault), "transcript_path": str(path)})

    result = Worker(vault).once()

    assert result["status"] == "PROCESSED"
    assert result["canonical_effect_count"] == 0
    assert result["review_effect_count"] == 1
    assert not MemoryStore(vault).load()["validated_memory"]
    review = ReviewStore(vault).list()
    assert len(review) == 1
    assert review[0]["status"] == "PENDING"
    assert review[0]["reason"] == "HUMAN_APPROVAL_REQUIRED"

    app = create_app(vault, token="b1-test-token", background=False)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        listed = client.get("/api/review/candidates", headers={"Authorization": "Bearer b1-test-token"})
    assert listed.status_code == 200
    assert listed.json()["candidates"][0]["project_id"] == project
    assert listed.json()["candidates"][0]["status"] == "PENDING"

    # Pending review data never enters the SessionStart V1 context.
    before = compile_context(vault, vault, "Continue the database work", event="SessionStart")
    assert "SQLite" not in before["context"]
    assert before["selected_ids"] == []

    item = review[0]
    accepted = review_action(vault, item["id"], "accept", {
        "expected_revision": MemoryStore(vault).revision(),
    })
    assert accepted["status"] == "ACCEPTED"
    assert len(MemoryStore(vault).load()["validated_memory"]) == 1

    # A repeated accept is terminal and cannot create a second memory.
    replay = review_action(vault, item["id"], "accept", {
        "expected_revision": MemoryStore(vault).revision(),
    })
    assert replay["status"] == "ACCEPTED"
    assert len(MemoryStore(vault).load()["validated_memory"]) == 1
    terminal = ReviewStore(vault).list()[0]
    assert "candidate" not in terminal
    assert terminal["candidate_fingerprint"].startswith("fp_")
    assert terminal["project_id"] == project

    after = compile_context(vault, vault, "Continue the database work", event="SessionStart")
    assert "SQLite" in after["context"]


def test_b1_rejection_is_durable_and_fingerprint_suppresses_replay(b1_runtime):
    vault, project = b1_runtime
    store = ReviewStore(vault)
    first = store.add(_candidate(project), "HUMAN_APPROVAL_REQUIRED", {
        "client": "claude", "evidence_id": "evd_" + "a" * 32,
        "session_hash": identity("session_", "b1-reject"), "role": "user",
    })
    assert first
    rejected = review_action(vault, first, "reject", {})
    assert rejected["status"] == "REJECTED"
    assert rejected["candidate_fingerprint"].startswith("fp_")
    assert rejected["project_id"] == project
    assert "candidate" not in rejected
    assert "SQLite" not in json.dumps(rejected)

    # A different candidate ID for the same project/content/evidence is the
    # same capture fingerprint and must remain suppressed.
    replay = store.add(_candidate(project, candidate_id="cand-b1-replay"), "HUMAN_APPROVAL_REQUIRED", {
        "client": "claude", "evidence_id": "evd_" + "a" * 32,
        "session_hash": identity("session_", "b1-reject-replay"), "role": "user",
    })
    assert replay == first
    assert ReviewStore(vault).list()[0]["status"] == "REJECTED"


def test_b1_flag_defaults_off_and_is_explicitly_toggleable(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    cfg = RuntimeConfig(vault)
    assert cfg.load()["b1_human_approval"] is False
    assert cfg.set_human_approval(True)["b1_human_approval"] is True
    assert cfg.load()["b1_human_approval"] is True
    assert cfg.set_human_approval(False)["b1_human_approval"] is False
