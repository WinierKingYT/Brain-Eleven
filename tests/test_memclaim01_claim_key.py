"""MEMCLAIM-01: same-topic memories must not silently stay active together.

Contract: docs/contracts/MEMCLAIM-01-CLAIM-KEY-SUPERSESSION-CONTRACT-DRAFT.md.
The human chooses ``claim_key`` at review time; a same-key conflict is shown,
never auto-resolved; the event time survives the worker boundary.
"""

import json
import re

import pytest

from brain_eleven.memory import MemoryStore
from brain_eleven.projects.registry import ProjectRegistry
from brain_eleven.memory.truth import MemoryTruthEngine, TruthAction
from brain_eleven.runtime.review import ReviewStore
from brain_eleven.runtime.service import create_app, review_action
from brain_eleven.runtime.worker import Worker, _memory_candidate_values, enqueue
from tests.test_memory_truth import _memory, _store
from tests.test_shadow_accept import _runtime

OLD_TIME = "2026-09-20T10:00:00.000Z"
NEW_TIME = "2026-09-23T09:00:00.000Z"


def _review_item(tmp_path, vault, session, text, timestamp):
    """Capture one real transcript line in SHADOW and return its review item."""
    slug = re.sub(r"[^A-Za-z0-9]", "-", str(vault.resolve()))
    directory = tmp_path / slug
    directory.mkdir(exist_ok=True)
    path = directory / f"{session}.jsonl"
    path.write_text(json.dumps({
        "type": "user", "sessionId": session, "timestamp": timestamp,
        "message": {"role": "user", "content": text},
    }) + "\n", encoding="utf-8")
    before = {x["id"] for x in ReviewStore(vault).list()}
    enqueue(vault, "claude", {"session_id": session, "cwd": str(vault), "transcript_path": str(path)})
    assert Worker(vault).once()["review_effect_count"] == 1
    (item,) = [x for x in ReviewStore(vault).list() if x["status"] == "PENDING" and x["id"] not in before]
    return item


def _accept(vault, item, **payload):
    return review_action(vault, item["id"], "accept", {"expected_revision": MemoryStore(vault).revision(), **payload})


def _active(vault):
    return [m for m in MemoryStore(vault).load()["validated_memory"] if m.get("status") == "active"]


def _empty_store(vault):
    _store(vault, [])
    root = vault / "root-brain-eleven"
    root.mkdir()
    ProjectRegistry(vault).register(root, project_id="brain-eleven", proactive_capture=True)


def _truth_candidate(**overrides):
    value = {"candidate_id": "cand-x", "content": "Use SQLite", "memory_type": "decision", "scope": "project",
             "project_id": "brain-eleven", "dedup_fingerprint": "new", "confidence": 1.0}
    value.update(overrides)
    return value


# C0 -- the worker allowlist no longer strips claim_key / occurred_at.

def test_worker_values_keep_claim_key_and_event_time():
    values = _memory_candidate_values({"candidate_id": "c", "content": "x", "claim_key": "srt-00.ship-status",
                                       "occurred_at": OLD_TIME, "unrelated": "dropped"})
    assert values["claim_key"] == "srt-00.ship-status"
    assert values["occurred_at"] == OLD_TIME
    assert "unrelated" not in values


def test_accepted_memory_keeps_the_transcript_event_time(tmp_path):
    vault, _ = _runtime(tmp_path, shadow_accept=True)
    item = _review_item(tmp_path, vault, "s-old", "We decided that SRT-00 is not ready to ship.", OLD_TIME)

    assert _accept(vault, item)["status"] == "ACCEPTED"

    (record,) = _active(vault)
    assert record["occurred_at"] == OLD_TIME
    assert record["timestamp"] == OLD_TIME


# C1 -- claim_key chosen by the human at acceptance.

def test_valid_claim_key_is_persisted(tmp_path):
    vault, _ = _runtime(tmp_path, shadow_accept=True)
    item = _review_item(tmp_path, vault, "s-old", "We decided that SRT-00 is not ready to ship.", OLD_TIME)

    assert _accept(vault, item, claim_key="  SRT-00.Ship-Status ")["status"] == "ACCEPTED"

    assert _active(vault)[0]["claim_key"] == "srt-00.ship-status"


@pytest.mark.parametrize("bad", ["no-separator", "has space.key", "../path.key", "x" * 81 + ".k", 7])
def test_invalid_claim_key_from_human_is_refused_without_writing(tmp_path, bad):
    vault, _ = _runtime(tmp_path, shadow_accept=True)
    item = _review_item(tmp_path, vault, "s-old", "We decided that SRT-00 is not ready to ship.", OLD_TIME)

    with pytest.raises(ValueError, match="claim_key"):
        _accept(vault, item, claim_key=bad)

    assert not MemoryStore(vault).load()["validated_memory"]
    assert ReviewStore(vault).list()[0]["status"] == "PENDING"


def test_invalid_claim_key_at_truth_boundary_is_cleared_and_recorded(tmp_path):
    _empty_store(tmp_path)
    MemoryTruthEngine(tmp_path).process([_truth_candidate(claim_key="Not A Key")], commit=True, commit_new=True)

    (record,) = MemoryStore(tmp_path).load()["validated_memory"]
    assert record["claim_key"] == ""
    assert "CLAIM_KEY_INVALID" in record["issues"]


# C2 -- replay of the 2026-09-23 SRT-00 incident shape.

def test_same_claim_key_conflict_is_shown_then_resolved_by_explicit_supersession(tmp_path):
    vault, _ = _runtime(tmp_path, shadow_accept=True)
    old = _review_item(tmp_path, vault, "s-old", "We decided that SRT-00 is not ready to ship.", OLD_TIME)
    assert _accept(vault, old, claim_key="srt-00.ship-status")["status"] == "ACCEPTED"
    (old_record,) = _active(vault)

    new = _review_item(tmp_path, vault, "s-new", "We decided that SRT-00 is closed and shipped.", NEW_TIME)
    blocked = _accept(vault, new, claim_key="srt-00.ship-status")

    assert blocked["status"] == "DEGRADED"
    assert blocked["conflict"]["memory_id"] == old_record["memory_id"]
    assert "not ready to ship" in blocked["conflict"]["content"]
    assert blocked["conflict"]["occurred_at"] == OLD_TIME
    assert [m["memory_id"] for m in _active(vault)] == [old_record["memory_id"]]
    pending = next(x for x in ReviewStore(vault).list() if x["id"] == new["id"])
    assert pending["status"] == "PENDING" and "accept_intent" not in pending

    resolved = _accept(vault, new, claim_key="srt-00.ship-status", target_id=old_record["memory_id"])

    assert resolved["status"] == "ACCEPTED"
    (current,) = _active(vault)
    assert "closed and shipped" in current["content"]
    assert current["claim_key"] == "srt-00.ship-status"
    assert current["occurred_at"] == NEW_TIME
    old_now = next(m for m in MemoryStore(vault).load()["validated_memory"] if m["memory_id"] == old_record["memory_id"])
    assert old_now["status"] == "superseded"


def test_explicit_supersession_still_detects_another_active_same_key(tmp_path):
    _store(tmp_path, [
        _memory("mem_target", "Use PostgreSQL", fingerprint="a", claim_key="db:selected"),
        _memory("mem_other", "Use MySQL", fingerprint="b", claim_key="db:selected"),
    ])
    result = MemoryTruthEngine(tmp_path).process([_truth_candidate(
        claim_key="db:selected", operation="SUPERSEDE_EXISTING", target_memory_id="mem_target",
        successor_memory_id="mem_new")], commit=True)

    assert result.decisions[0].action == TruthAction.CONFLICT.value
    assert result.decisions[0].target_memory_id == "mem_other"
    assert {m["memory_id"] for m in MemoryStore(tmp_path).load()["validated_memory"] if m["status"] == "active"} == {"mem_target", "mem_other"}


# C3 -- event time validation.

@pytest.mark.parametrize("value", ["2026-09-20", OLD_TIME, "2026-09-20T10:00:00+03:00"])
def test_valid_event_time_is_persisted(tmp_path, value):
    _empty_store(tmp_path)
    MemoryTruthEngine(tmp_path).process([_truth_candidate(occurred_at=value)], commit=True, commit_new=True)

    (record,) = MemoryStore(tmp_path).load()["validated_memory"]
    assert record["occurred_at"] == value
    assert "OCCURRED_AT_INVALID" not in record["issues"]


@pytest.mark.parametrize("value", ["yesterday", "2026-09-20T10:00:00", "2026-13-40"])
def test_invalid_event_time_is_cleared_and_recorded(tmp_path, value):
    _empty_store(tmp_path)
    MemoryTruthEngine(tmp_path).process([_truth_candidate(occurred_at=value)], commit=True, commit_new=True)

    (record,) = MemoryStore(tmp_path).load()["validated_memory"]
    assert record["occurred_at"] == ""
    assert record["timestamp"] != value
    assert "OCCURRED_AT_INVALID" in record["issues"]


# C4 -- evidence references stay opaque identifiers.

def test_opaque_evidence_refs_are_persisted_and_paths_are_dropped(tmp_path):
    _empty_store(tmp_path)
    refs = ["evidence_ab12", "sha256:deadbeef", "C:\\Users\\x\\session.jsonl", "/home/x/t.jsonl", "has space"]
    MemoryTruthEngine(tmp_path).process([_truth_candidate(evidence_refs=refs)], commit=True, commit_new=True)

    (record,) = MemoryStore(tmp_path).load()["validated_memory"]
    assert record["evidence_refs"] == ["evidence_ab12", "sha256:deadbeef"]
    assert "EVIDENCE_REF_DROPPED" in record["issues"]


# Review listing offers the project's existing keys for reuse.

def test_candidate_listing_offers_existing_active_claim_keys(tmp_path):
    from fastapi.testclient import TestClient

    vault, _ = _runtime(tmp_path, shadow_accept=True)
    old = _review_item(tmp_path, vault, "s-old", "We decided that SRT-00 is not ready to ship.", OLD_TIME)
    _accept(vault, old, claim_key="srt-00.ship-status")
    _review_item(tmp_path, vault, "s-new", "We decided that SRT-00 is closed and shipped.", NEW_TIME)

    client = TestClient(create_app(vault, token="t", background=False), base_url="http://127.0.0.1")
    listed = client.get("/api/review/candidates", headers={"Authorization": "Bearer t"}).json()["candidates"]

    (pending,) = [x for x in listed if x["status"] == "PENDING"]
    assert pending["claim_keys"] == ["srt-00.ship-status"]
