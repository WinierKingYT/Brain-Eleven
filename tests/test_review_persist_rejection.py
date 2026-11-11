"""A candidate the safety gate refuses must not drop the whole capture job.

Real dead letters (2026-10/11): every REVIEW_PERSIST_FAILED job had a user
message over the capture line limit (``too_many_lines``). The refusal is
permanent, so retrying it three times lost every other candidate of the
session. Refusals are counted (no text); real persistence failures still retry.
"""

import json
import re

import pytest

from brain_eleven.projects.registry import ProjectRegistry
from brain_eleven.runtime import triage, worker as worker_mod
from brain_eleven.runtime.capture_queue import CaptureQueue
from brain_eleven.runtime.migration import migrate
from brain_eleven.runtime.review import ReviewStore
from brain_eleven.runtime.storage import RuntimeConfig, write_json
from brain_eleven.runtime.worker import RETRYABLE_DEAD_LETTER_CODES, Worker, enqueue
from brain_eleven.state import StateService

GOOD = "We decided to use SQLite for B1 capture."
SECRET_LIKE = "We decided the deploy password = hunter2hunter2 stays."


@pytest.fixture
def vault(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    project = ProjectRegistry(vault).register(vault, proactive_capture=True)
    StateService(vault).init_project(project["project_id"], source={"type": "user", "reference": "rpf"})
    migrate(vault)
    write_json(RuntimeConfig(vault).path, {
        "schema_version": 1, "mode": "CANARY", "project_ids": [project["project_id"]],
        "local_model": None, "b1_human_approval": True,
        "transcript_roots": {"claude": [str(tmp_path)], "codex": [str(tmp_path)]},
    })
    return vault


def _enqueue(vault, tmp_path, *texts):
    slug = re.sub(r"[^A-Za-z0-9]", "-", str(vault.resolve()))
    directory = tmp_path / slug
    directory.mkdir(exist_ok=True)
    path = directory / "rpf-session.jsonl"
    path.write_text("".join(json.dumps({
        "type": "user", "sessionId": "rpf-session",
        "message": {"role": "user", "content": text},
    }) + "\n" for text in texts), encoding="utf-8")
    enqueue(vault, "claude", {"session_id": "rpf-session", "cwd": str(vault), "transcript_path": str(path)})


def _with_extra_candidates(monkeypatch, *contents):
    def extra(provider, message, project_id):
        return [{"candidate_id": f"cand-extra-{i}", "candidate_type": "NEW_MEMORY", "project_id": project_id,
                 "scope": "project", "content": content, "memory_type": "decision", "commitment": "COMMITTED",
                 "confidence": 0.9, "evidence_refs": [message.record.evidence_id]}
                for i, content in enumerate(contents)]
    monkeypatch.setattr(worker_mod, "_semantic_review_candidates", extra)


def _pending(vault):
    return [x for x in ReviewStore(vault).list() if x.get("status") == "PENDING"]


@pytest.mark.parametrize("bad, rule", [
    (SECRET_LIKE, "UNSAFE_POTENTIAL_SECRET"),
    ("We decided " + "x" * 8100, "UNSAFE_PAYLOAD_TOO_LARGE"),
    ("We decided:\n" + "\n".join(f"line {i}" for i in range(90)), "UNSAFE_TOO_MANY_LINES"),
])
def test_refused_candidate_is_counted_and_job_completes(vault, tmp_path, monkeypatch, bad, rule):
    _with_extra_candidates(monkeypatch, bad, "We decided to keep the review queue under fifty items.")
    _enqueue(vault, tmp_path, GOOD)

    result = Worker(vault).once()

    assert result["status"] == "PROCESSED"
    contents = [x["candidate"]["content"] for x in _pending(vault)]
    assert GOOD in contents and "We decided to keep the review queue under fifty items." in contents
    assert bad not in contents
    assert triage.summary(vault)["by_rule"] == {rule: 1}
    assert not list((CaptureQueue(vault).root / "dead-letter").glob("cap_*.json"))
    # The refused text is written nowhere in the runtime state.
    runtime = RuntimeConfig(vault).root
    assert not any(bad[:40] in p.read_text(encoding="utf-8", errors="ignore")
                   for p in runtime.rglob("*.json") if "evidence" not in p.parts)


def test_real_transcript_with_too_many_lines_message_keeps_other_candidates(vault, tmp_path):
    # The measured real cause: one long multi-line user message in the session.
    long_message = "We decided to paste the log below:\n" + "\n".join(f"step {i} done" for i in range(120))
    _enqueue(vault, tmp_path, GOOD, long_message)

    result = Worker(vault).once()

    assert result["status"] == "PROCESSED"
    assert [x["candidate"]["content"] for x in _pending(vault)] == [GOOD]
    assert triage.summary(vault)["by_rule"].get("UNSAFE_TOO_MANY_LINES", 0) >= 1


def test_real_persistence_failure_still_retries(vault, tmp_path, monkeypatch):
    monkeypatch.setattr(ReviewStore, "add", lambda self, candidate, reason, source: None)
    _enqueue(vault, tmp_path, GOOD)

    result = Worker(vault).once()

    assert result["error"] == "REVIEW_PERSIST_FAILED"
    assert result["status"] != "PROCESSED"
    assert "UNSAFE_" not in json.dumps(triage.summary(vault))


def test_rejection_reports_safety_code_without_changing_add():
    store = ReviewStore.__new__(ReviewStore)
    assert store.rejection({"content": GOOD}) is None
    assert store.rejection({"content": SECRET_LIKE}) == "UNSAFE_POTENTIAL_SECRET"
    assert store.rejection({"content": 42}) == "UNSAFE_NOT_TEXT"
    assert store.rejection({"candidate_type": "STATE_MUTATION", "text": "x\n" * 100}) == "UNSAFE_TOO_MANY_LINES"


def test_review_persist_failed_is_retryable_dead_letter_code():
    assert "REVIEW_PERSIST_FAILED" in RETRYABLE_DEAD_LETTER_CODES
