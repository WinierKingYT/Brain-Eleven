"""W-03B native transcript ownership and stable-source boundaries."""

from __future__ import annotations

import hashlib
import json

import pytest

from brain_eleven.memory import MemoryStore
from brain_eleven.projects.registry import ProjectRegistry
from brain_eleven.runtime.evidence import read_increment
from brain_eleven.runtime.migration import migrate
from brain_eleven.runtime.ownership import TranscriptOwnershipError, verify_transcript_ownership
from brain_eleven.runtime.storage import RuntimeConfig, write_json
from brain_eleven.runtime.worker import Worker, enqueue
from brain_eleven.state import StateService


def _slug(root):
    return str(root.resolve()).replace(":", "-").replace("/", "-").replace("\\", "-")


@pytest.fixture
def runtime(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    project = ProjectRegistry(vault).register(vault, proactive_capture=True)
    StateService(vault).init_project(project["project_id"], source={"type": "user", "reference": "w03b"})
    migrate(vault)
    write_json(RuntimeConfig(vault).path, {
        "schema_version": 1,
        "mode": "CANARY",
        "project_ids": [project["project_id"]],
        "local_model": None,
        "transcript_roots": {"claude": [str(tmp_path)], "codex": [str(tmp_path)]},
    })
    return vault, project["project_id"]


def _claude_transcript(tmp_path, raw_session, content="We decided to use SQLite.", *, session_id=None):
    session_id = session_id or raw_session
    directory = tmp_path / _slug(tmp_path / "vault")
    directory.mkdir(exist_ok=True)
    path = directory / (raw_session + ".jsonl")
    path.write_text(json.dumps({
        "type": "user",
        "sessionId": session_id,
        "message": {"role": "user", "content": content},
    }) + "\n", encoding="utf-8")
    return path


def _codex_transcript(tmp_path, raw_session, project_root, content="We decided to use SQLite."):
    path = tmp_path / (raw_session + ".jsonl")
    path.write_text("\n".join([
        json.dumps({"type": "session_meta", "payload": {"session_id": raw_session, "cwd": str(project_root)}}),
        json.dumps({"type": "response_item", "payload": {"type": "message", "role": "user", "content": content}}),
    ]) + "\n", encoding="utf-8")
    return path


def test_matching_native_clients_are_owned_and_captured_once(runtime, tmp_path):
    vault, project_id = runtime
    claude = _claude_transcript(tmp_path, "claude-match")
    codex = _codex_transcript(tmp_path, "codex-match", vault)
    for client, raw_session, path in (("claude", "claude-match", claude), ("codex", "codex-match", codex)):
        result = enqueue(vault, client, {"session_id": raw_session, "cwd": str(vault), "transcript_path": str(path)})
        assert Worker(vault).once()["status"] == "PROCESSED", result
    assert len(MemoryStore(vault).load()["validated_memory"]) == 1


def test_foreign_session_is_terminal_before_evidence_persistence(runtime, tmp_path):
    vault, _ = runtime
    path = _claude_transcript(tmp_path, "expected-session", session_id="foreign-session")
    enqueue(vault, "claude", {"session_id": "expected-session", "cwd": str(vault), "transcript_path": str(path)})
    result = Worker(vault).once()
    assert result == {"status": "DEAD_LETTER", "error": "TRANSCRIPT_OWNERSHIP_MISMATCH", "job_id": result["job_id"]}
    assert not list((vault / ".brain-eleven" / "capture" / "evidence").glob("*.json"))
    assert not MemoryStore(vault).load()["validated_memory"]


def test_unknown_metadata_is_terminal_and_content_free(runtime, tmp_path):
    vault, _ = runtime
    path = tmp_path / (_slug(vault) + ".jsonl")
    path.write_text(json.dumps({"type": "user", "message": {"role": "user", "content": "private"}}) + "\n", encoding="utf-8")
    enqueue(vault, "claude", {"session_id": "unknown", "cwd": str(vault), "transcript_path": str(path)})
    result = Worker(vault).once()
    assert result["status"] == "DEAD_LETTER"
    assert result["error"] == "TRANSCRIPT_OWNERSHIP_UNVERIFIED"
    ledger = (vault / ".brain-eleven" / "capture" / "capture-ledger.jsonl").read_text(encoding="utf-8")
    assert "private" not in ledger and str(path) not in ledger


def test_foreign_project_slug_is_rejected(runtime, tmp_path):
    vault, first_id = runtime
    foreign_root = tmp_path / "foreign-project"
    foreign_root.mkdir()
    second = ProjectRegistry(vault).register(foreign_root, proactive_capture=True)
    path = _claude_transcript(tmp_path, "project-session")
    # Place the native transcript under the second project's exact Claude slug.
    foreign_dir = tmp_path / _slug(foreign_root)
    foreign_dir.mkdir(exist_ok=True)
    foreign_path = foreign_dir / "project-session.jsonl"
    foreign_path.write_bytes(path.read_bytes())
    enqueue(vault, "claude", {"session_id": "project-session", "cwd": str(vault), "transcript_path": str(foreign_path)})
    result = Worker(vault).once()
    assert result["status"] == "DEAD_LETTER"
    assert result["error"] == "TRANSCRIPT_OWNERSHIP_MISMATCH"
    assert first_id != second["project_id"]
    assert not MemoryStore(vault).load()["validated_memory"]


def test_same_size_replacement_after_ownership_validation_is_detected(runtime, tmp_path):
    vault, project_id = runtime
    path = _claude_transcript(tmp_path, "stable-session", "A message with stable size.")
    session = "claude:" + hashlib.sha256(b"stable-session").hexdigest()
    binding = verify_transcript_ownership(vault, path, "claude", session, project_id, vault)
    replacement = json.dumps({
        "type": "user", "sessionId": "stable-session",
        "message": {"role": "user", "content": "A message with changed size."},
    }) + "\n"
    assert len(replacement.encode()) == path.stat().st_size
    path.write_text(replacement, encoding="utf-8")
    with pytest.raises(ValueError, match="TRANSCRIPT_CHANGED"):
        read_increment(vault, path, "claude", session, project_id, "2026-09-13T00:00:00Z", binding=binding)


def test_claude_slug_collision_abstains_before_read(runtime, tmp_path, monkeypatch):
    vault, project_id = runtime
    path = _claude_transcript(tmp_path, "collision-session")
    registry = ProjectRegistry(vault)
    record = registry.get(project_id)
    monkeypatch.setattr(ProjectRegistry, "list_projects", lambda _self: [
        record,
        {**record, "project_id": "proj_collision"},
    ])
    session = "claude:" + hashlib.sha256(b"collision-session").hexdigest()
    with pytest.raises(TranscriptOwnershipError) as exc:
        verify_transcript_ownership(vault, path, "claude", session, project_id, vault)
    assert exc.value.code == "TRANSCRIPT_OWNERSHIP_UNVERIFIED"
