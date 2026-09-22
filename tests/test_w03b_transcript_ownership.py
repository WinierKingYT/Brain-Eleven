"""W-03B native transcript ownership and stable-source boundaries."""

from __future__ import annotations

import hashlib
import json
import os
import re

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
    """Mirror brain_eleven.runtime.ownership._project_slug exactly (the real
    Claude Code CLI's own project-directory slug: every character outside
    [A-Za-z0-9] becomes a literal "-", one hyphen per character)."""
    return re.sub(r"[^A-Za-z0-9]", "-", str(root.resolve()))


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
    payload = (
        json.dumps({
            "type": "user",
            "sessionId": session_id,
            "message": {"role": "user", "content": content},
        }, ensure_ascii=False, separators=(",", ":")) + "\n"
    ).encode("utf-8")
    path.write_bytes(payload)
    return path


def _codex_transcript(tmp_path, raw_session, project_root, content="We decided to use SQLite."):
    path = tmp_path / (raw_session + ".jsonl")
    payload = b"\n".join([
        json.dumps({
            "type": "session_meta",
            "payload": {"session_id": raw_session, "cwd": str(project_root)},
        }, ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
        json.dumps({
            "type": "response_item",
            "payload": {"type": "message", "role": "user", "content": content},
        }, ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
    ]) + b"\n"
    path.write_bytes(payload)
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
    replacement_bytes = (
        json.dumps({
            "type": "user", "sessionId": "stable-session",
            "message": {"role": "user", "content": "A message with edited size."},
        }, ensure_ascii=False, separators=(",", ":")) + "\n"
    ).encode("utf-8")
    assert len(replacement_bytes) == path.stat().st_size
    path.write_bytes(replacement_bytes)
    with pytest.raises(ValueError, match="TRANSCRIPT_CHANGED"):
        read_increment(vault, path, "claude", session, project_id, "2026-09-13T00:00:00Z", binding=binding)


def _claude_line(session_id, content):
    return (
        json.dumps({
            "type": "user", "sessionId": session_id,
            "message": {"role": "user", "content": content},
        }, ensure_ascii=False, separators=(",", ":")) + "\n"
    ).encode("utf-8")


def test_same_size_replacement_with_a_new_inode_is_detected(runtime, tmp_path):
    vault, project_id = runtime
    path = _claude_transcript(tmp_path, "inode-session", "A message with stable size.")
    session = "claude:" + hashlib.sha256(b"inode-session").hexdigest()
    binding = verify_transcript_ownership(vault, path, "claude", session, project_id, vault)
    replacement_bytes = _claude_line("inode-session", "A message with edited size.")
    assert len(replacement_bytes) == path.stat().st_size
    sibling = path.with_name("inode-session.replacement")
    sibling.write_bytes(replacement_bytes)
    original_identity = (path.stat().st_dev, path.stat().st_ino)
    os.replace(sibling, path)
    assert (path.stat().st_dev, path.stat().st_ino) != original_identity
    with pytest.raises(ValueError, match="TRANSCRIPT_CHANGED"):
        read_increment(vault, path, "claude", session, project_id, "2026-09-13T00:00:00Z", binding=binding)


def test_multibyte_replacement_with_identical_byte_length_is_detected(runtime, tmp_path):
    vault, project_id = runtime
    original_content = "A message with stable size."
    path = _claude_transcript(tmp_path, "multibyte-session", original_content)
    session = "claude:" + hashlib.sha256(b"multibyte-session").hexdigest()
    binding = verify_transcript_ownership(vault, path, "claude", session, project_id, vault)
    # Two ASCII bytes are swapped for one two-byte UTF-8 character.
    replacement_bytes = _claude_line("multibyte-session", original_content[:-2] + "é")
    assert len(replacement_bytes) == path.stat().st_size
    assert replacement_bytes != path.read_bytes()
    path.write_bytes(replacement_bytes)
    with pytest.raises(ValueError, match="TRANSCRIPT_CHANGED"):
        read_increment(vault, path, "claude", session, project_id, "2026-09-13T00:00:00Z", binding=binding)


def test_worker_preserves_changed_code_and_writes_no_effect(runtime, tmp_path, monkeypatch):
    vault, _ = runtime
    path = _claude_transcript(tmp_path, "worker-stable", "A message with stable size.")
    enqueue(vault, "claude", {
        "session_id": "worker-stable",
        "cwd": str(vault),
        "transcript_path": str(path),
    })
    import brain_eleven.runtime.worker as worker_module

    original_verify = worker_module.verify_transcript_ownership
    replacement_bytes = (
        json.dumps({
            "type": "user", "sessionId": "worker-stable",
            "message": {"role": "user", "content": "A message with edited size."},
        }, ensure_ascii=False, separators=(",", ":")) + "\n"
    ).encode("utf-8")
    assert len(replacement_bytes) == path.stat().st_size

    def replace_after_verify(*args, **kwargs):
        binding = original_verify(*args, **kwargs)
        path.write_bytes(replacement_bytes)
        return binding

    monkeypatch.setattr(worker_module, "verify_transcript_ownership", replace_after_verify)
    result = Worker(vault).once()
    assert result["status"] == "QUEUED"
    assert result["error"] == "TRANSCRIPT_CHANGED"
    assert not list((vault / ".brain-eleven" / "capture" / "evidence").glob("*.json"))
    assert not MemoryStore(vault).load()["validated_memory"]


def test_project_root_with_underscore_is_captured_not_dead_lettered(tmp_path):
    """W-07B capture-silent-gap: a project root containing an underscore (or
    any other non-alphanumeric character besides ``:``/``/``/``\\``) must
    still resolve to the real Claude Code CLI's transcript directory slug.

    The CLI converts *every* character outside ``[A-Za-z0-9]`` to ``-``
    (verified empirically against a real ``claude`` invocation whose cwd
    contained ``_``, ``.``, a space, ``+``, parentheses and ``~`` -- every
    one became a single ``-``). Before this fix, ``_project_slug`` only
    substituted ``:``, ``/`` and ``\\``, so a project root with an
    underscore anywhere in it (routine for ``tempfile.TemporaryDirectory``
    suffixes) produced a slug that could never match the directory the real
    client actually wrote transcripts to. ``verify_transcript_ownership``
    then found zero matching registry entries and dead-lettered every
    capture for that project with the terminal code
    ``TRANSCRIPT_OWNERSHIP_UNVERIFIED`` -- silently, with no error surfaced
    anywhere else in the pipeline (not stuck, not retried, never enqueued
    again), while a sibling project with no underscore in its root captured
    normally in the same run. This is what made W-07B's dogfood harness
    report Finding 3 as an inconsistent multi-project capture gap: the
    dependency was never "which project" or "how many projects" -- it was
    always "does this project's absolute path contain a character the old
    slug function did not convert."
    """
    vault = tmp_path / "vault_with_underscore"
    vault.mkdir()
    project = ProjectRegistry(vault).register(vault, proactive_capture=True)
    StateService(vault).init_project(project["project_id"], source={"type": "user", "reference": "w07b"})
    migrate(vault)
    write_json(RuntimeConfig(vault).path, {
        "schema_version": 1,
        "mode": "CANARY",
        "project_ids": [project["project_id"]],
        "local_model": None,
        "transcript_roots": {"claude": [str(tmp_path)], "codex": [str(tmp_path)]},
    })

    # Mirror the real client: every non-alphanumeric character (including
    # the underscore this test root deliberately contains) becomes "-".
    directory = tmp_path / _slug(vault)
    directory.mkdir(exist_ok=True)
    path = directory / "underscore-session.jsonl"
    path.write_bytes((json.dumps({
        "type": "user", "sessionId": "underscore-session",
        "message": {"role": "user", "content": "We decided to use SQLite."},
    }, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8"))

    enqueue(vault, "claude", {"session_id": "underscore-session", "cwd": str(vault), "transcript_path": str(path)})
    result = Worker(vault).once()

    assert result["status"] == "PROCESSED", result
    assert len(MemoryStore(vault).load()["validated_memory"]) == 1
    ledger = (vault / ".brain-eleven" / "capture" / "capture-ledger.jsonl").read_text(encoding="utf-8")
    assert "DEAD_LETTER" not in ledger
    assert not list((vault / ".brain-eleven" / "capture" / "dead-letter").glob("*.json"))


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
