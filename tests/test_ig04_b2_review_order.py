"""Focused IG-04 B2 review deduplication and ordering tests."""

import json
from datetime import datetime, timedelta, timezone

import pytest

from brain_eleven.memory import MemoryStore
from brain_eleven.projects.registry import ProjectRegistry
from brain_eleven.runtime.migration import migrate
from brain_eleven.runtime.review import ReviewStore
from brain_eleven.runtime.service import review_action
from brain_eleven.runtime.storage import RuntimeConfig, write_json
from brain_eleven.state import StateService


@pytest.fixture
def b2_runtime(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    project = ProjectRegistry(vault).register(vault, proactive_capture=True)
    StateService(vault).init_project(project["project_id"], source={"type": "user", "reference": "ig04-b2"})
    migrate(vault)
    write_json(RuntimeConfig(vault).path, {
        "schema_version": 1,
        "mode": "CANARY",
        "project_ids": [project["project_id"]],
        "local_model": None,
        "b1_human_approval": True,
    })
    return vault, project["project_id"]


def _candidate(project_id, candidate_id, content, *, confidence=0.5, evidence="evd-a",
               candidate_type="NEW_MEMORY"):
    value = {
        "candidate_id": candidate_id,
        "candidate_type": candidate_type,
        "project_id": project_id,
        "scope": "project",
        "memory_type": "decision",
        "commitment": "COMMITTED",
        "confidence": confidence,
        "evidence_refs": [evidence],
    }
    value["text" if candidate_type == "STATE_MUTATION" else "content"] = content
    if candidate_type == "STATE_MUTATION":
        value["operation"] = "ADD_BLOCKER"
    return value


def _source(evidence):
    return {"client": "claude", "evidence_id": evidence, "role": "user",
            "session_hash": "session_" + "a" * 64}


def _set_created(store, review_id, value):
    item = store.path(review_id)
    record = json.loads(item.read_text(encoding="utf-8"))
    record["created_at"] = value
    write_json(item, record)


def test_b2_hides_pending_duplicates_and_finalizes_the_group_once(b2_runtime):
    vault, project = b2_runtime
    store = ReviewStore(vault)
    content = "We decided to keep the queue local."
    first = store.add(_candidate(project, "cand-b2-a", content, confidence=0.40, evidence="evd-a"),
                      "HUMAN_APPROVAL_REQUIRED", _source("evd-a"))
    second = store.add(_candidate(project, "cand-b2-b", content, confidence=0.90, evidence="evd-b"),
                       "HUMAN_APPROVAL_REQUIRED", _source("evd-b"))
    assert first != second
    assert len(list(store.root.glob("rev_*.json"))) == 2

    visible = [item for item in store.list() if item["status"] == "PENDING"]
    assert [item["id"] for item in visible] == [second]
    assert visible[0]["duplicate_count"] == 1
    duplicate = json.loads(store.path(first).read_text(encoding="utf-8"))
    assert duplicate["duplicate_of"] == second
    assert duplicate["candidate"]["evidence_refs"] == ["evd-a"]

    accepted = review_action(vault, second, "accept", {"expected_revision": MemoryStore(vault).revision()})
    assert accepted["status"] == "ACCEPTED"
    assert len(MemoryStore(vault).load()["validated_memory"]) == 1
    terminal = [json.loads(path.read_text(encoding="utf-8")) for path in store.root.glob("rev_*.json")]
    assert {item["status"] for item in terminal} == {"ACCEPTED"}
    assert {tuple(item["evidence_refs"]) for item in terminal} == {("evd-a",), ("evd-b",)}
    assert all("candidate" not in item for item in terminal)


def test_b2_review_order_is_fixed_by_confidence_age_type_and_id(b2_runtime):
    vault, project = b2_runtime
    store = ReviewStore(vault)
    records = [
        ("low", _candidate(project, "cand-low", "Low confidence", confidence=0.20, evidence="evd-low"), "2026-01-03T00:00:00+00:00"),
        ("recent", _candidate(project, "cand-recent", "Recent high confidence", confidence=0.90, evidence="evd-recent"), "2026-02-01T00:00:00+00:00"),
        ("old-memory", _candidate(project, "cand-old-memory", "Old high confidence", confidence=0.90, evidence="evd-old"), "2026-01-01T00:00:00+00:00"),
        ("old-state", _candidate(project, "cand-old-state", "Old state", confidence=0.90, evidence="evd-state", candidate_type="STATE_MUTATION"), "2026-01-01T00:00:00+00:00"),
    ]
    for _, candidate, created in records:
        review_id = store.add(candidate, "HUMAN_APPROVAL_REQUIRED", _source(candidate["evidence_refs"][0]))
        _set_created(store, review_id, created)

    expected = ["cand-old-state", "cand-old-memory", "cand-recent", "cand-low"]
    first = [item["candidate"]["candidate_id"] for item in store.list() if item["status"] == "PENDING"]
    second = [item["candidate"]["candidate_id"] for item in store.list() if item["status"] == "PENDING"]
    assert first == expected
    assert second == expected
    assert all(item["duplicate_count"] == 0 for item in store.list() if item["status"] == "PENDING")


def test_b2_content_groups_are_project_scoped(b2_runtime):
    vault, project = b2_runtime
    store = ReviewStore(vault)
    first = store.add(_candidate(project, "cand-project", "Same content", evidence="evd-project"),
                      "HUMAN_APPROVAL_REQUIRED", _source("evd-project"))
    foreign = store.add(_candidate("foreign-project", "cand-foreign", "Same content", evidence="evd-foreign"),
                        "HUMAN_APPROVAL_REQUIRED", _source("evd-foreign"))
    assert first != foreign
    pending = [item for item in store.list() if item["status"] == "PENDING"]
    assert {item["candidate"]["project_id"] for item in pending} == {project, "foreign-project"}
    assert all(item["duplicate_count"] == 0 for item in pending)


def test_b2_keeps_b1_expiry_per_candidate(b2_runtime):
    vault, project = b2_runtime
    store = ReviewStore(vault)
    first = store.add(_candidate(project, "cand-expire-a", "Expiry content", evidence="evd-expire-a"),
                      "HUMAN_APPROVAL_REQUIRED", _source("evd-expire-a"))
    second = store.add(_candidate(project, "cand-expire-b", "Expiry content", evidence="evd-expire-b"),
                       "HUMAN_APPROVAL_REQUIRED", _source("evd-expire-b"))
    expired = datetime.now(timezone.utc) - timedelta(days=1)
    future = datetime.now(timezone.utc) + timedelta(days=1)
    for review_id, timestamp in ((first, expired), (second, future)):
        record = json.loads(store.path(review_id).read_text(encoding="utf-8"))
        record["expires_at"] = timestamp.isoformat()
        write_json(store.path(review_id), record)

    store.expire()
    assert json.loads(store.path(first).read_text(encoding="utf-8"))["status"] == "EXPIRED"
    assert json.loads(store.path(second).read_text(encoding="utf-8"))["status"] == "PENDING"
    assert [item["id"] for item in store.list() if item["status"] == "PENDING"] == [second]
