"""W-03A transcript-root confinement tests."""

from __future__ import annotations

import json

import pytest

from brain_eleven.memory import MemoryStore
from brain_eleven.projects.registry import ProjectRegistry
from brain_eleven.runtime.migration import migrate
from brain_eleven.runtime.storage import RuntimeConfig, write_json
from brain_eleven.runtime.worker import Worker, enqueue
from brain_eleven.state import StateService
from capture_provenance import TranscriptProvenanceError, resolve_transcript_path


def _runtime(tmp_path, *, roots):
    vault = tmp_path / "vault"
    vault.mkdir()
    project = ProjectRegistry(vault).register(vault, proactive_capture=True)
    StateService(vault).init_project(project["project_id"], source={"type": "user", "reference": "w03a"})
    migrate(vault)
    write_json(RuntimeConfig(vault).path, {
        "schema_version": 1,
        "mode": "CANARY",
        "project_ids": [project["project_id"]],
        "local_model": None,
        "transcript_roots": {"claude": [str(roots)], "codex": [str(roots)]},
    })
    return vault, project["project_id"]


def test_resolver_accepts_root_confined_file_and_rejects_foreign_file(tmp_path):
    root = tmp_path / "trusted"
    root.mkdir()
    transcript = root / "session.jsonl"
    transcript.write_text("{}\n", encoding="utf-8")
    vault = tmp_path / "vault"
    vault.mkdir()
    write_json(RuntimeConfig(vault).path, {
        "schema_version": 1,
        "mode": "SHADOW",
        "project_ids": [],
        "local_model": None,
        "transcript_roots": {"claude": [str(root)], "codex": [str(root)]},
    })

    assert resolve_transcript_path(vault, "claude", transcript) == transcript.resolve()
    foreign = tmp_path / "foreign.jsonl"
    foreign.write_text("{}\n", encoding="utf-8")
    with pytest.raises(TranscriptProvenanceError) as exc:
        resolve_transcript_path(vault, "claude", foreign)
    assert exc.value.code == "TRANSCRIPT_PROVENANCE_SCOPE"


def test_resolver_rejects_source_symlink_even_when_target_is_confined(tmp_path):
    root = tmp_path / "trusted"
    root.mkdir()
    target = root / "target.jsonl"
    target.write_text("{}\n", encoding="utf-8")
    link = root / "link.jsonl"
    try:
        link.symlink_to(target)
    except OSError:
        pytest.skip("symlink creation is unavailable on this host")
    vault = tmp_path / "vault"
    vault.mkdir()
    write_json(RuntimeConfig(vault).path, {
        "schema_version": 1,
        "mode": "SHADOW",
        "project_ids": [],
        "local_model": None,
        "transcript_roots": {"claude": [str(root)], "codex": [str(root)]},
    })

    with pytest.raises(TranscriptProvenanceError) as exc:
        resolve_transcript_path(vault, "claude", link)
    assert exc.value.code == "TRANSCRIPT_PROVENANCE_SYMLINK"


@pytest.mark.parametrize("source_kind", ["relative", "parent", "unknown_client", "missing"])
def test_resolver_rejects_untrusted_locator_variants(tmp_path, source_kind):
    root = tmp_path / "trusted"
    root.mkdir()
    vault = tmp_path / "vault"
    vault.mkdir()
    write_json(RuntimeConfig(vault).path, {
        "schema_version": 1,
        "mode": "SHADOW",
        "project_ids": [],
        "local_model": None,
        "transcript_roots": {"claude": [str(root)], "codex": [str(root)]},
    })
    if source_kind == "relative":
        source = "session.jsonl"
        client = "claude"
    elif source_kind == "parent":
        source = root / ".." / "outside.jsonl"
        source.resolve().write_text("{}\n", encoding="utf-8")
        client = "claude"
    elif source_kind == "unknown_client":
        source = root / "session.jsonl"
        source.write_text("{}\n", encoding="utf-8")
        client = "other"
    else:
        source = root / "missing.jsonl"
        client = "claude"

    with pytest.raises(TranscriptProvenanceError) as exc:
        resolve_transcript_path(vault, client, source)
    assert exc.value.code.startswith("TRANSCRIPT_PROVENANCE_")


def test_enqueue_rejects_foreign_transcript_before_queue_effect(tmp_path):
    trusted = tmp_path / "trusted"
    foreign = tmp_path / "foreign"
    trusted.mkdir()
    foreign.mkdir()
    transcript = foreign / "session.jsonl"
    transcript.write_text(json.dumps({"type": "user", "message": {"role": "user", "content": "secret"}}) + "\n", encoding="utf-8")
    vault, _ = _runtime(tmp_path, roots=trusted)

    result = enqueue(vault, "claude", {
        "session_id": "foreign-source",
        "cwd": str(vault),
        "transcript_path": str(transcript),
    })

    assert result == {"status": "DEGRADED", "error": "TRANSCRIPT_PROVENANCE_SCOPE"}
    assert not list((vault / ".brain-eleven" / "capture" / "queued").glob("*.json"))
    assert not (vault / ".brain-eleven" / "capture" / "evidence").exists()
    assert not MemoryStore(vault).load()["validated_memory"]


def test_worker_revalidates_root_before_evidence_read(tmp_path):
    trusted = tmp_path / "trusted"
    replacement = tmp_path / "replacement"
    trusted.mkdir()
    replacement.mkdir()
    transcript = trusted / "session.jsonl"
    transcript.write_text(json.dumps({"type": "user", "message": {"role": "user", "content": "A bounded test statement."}}) + "\n", encoding="utf-8")
    vault, _ = _runtime(tmp_path, roots=trusted)
    receipt = enqueue(vault, "claude", {
        "session_id": "root-change",
        "cwd": str(vault),
        "transcript_path": str(transcript),
    })
    config = RuntimeConfig(vault).load()
    config["transcript_roots"] = {"claude": [str(replacement)], "codex": [str(replacement)]}
    write_json(RuntimeConfig(vault).path, config)

    result = Worker(vault).once()

    assert result["status"] == "QUEUED"
    assert result["error"] == "TRANSCRIPT_PROVENANCE_SCOPE"
    assert receipt["job_id"]
    assert not MemoryStore(vault).load()["validated_memory"]
