"""IG-04 B1 P2 coverage for recovery and project-scoped review isolation.

These tests intentionally exercise the already-implemented B1 behavior.  They
do not change the acceptance/rejection or canonical write paths.
"""

import json

import pytest

from brain_eleven.memory import MemoryStore
from brain_eleven.projects.registry import ProjectRegistry
from brain_eleven.runtime import service as service_module
from brain_eleven.runtime.migration import migrate
from brain_eleven.runtime.review import ReviewStore
from brain_eleven.runtime.service import review_action
from brain_eleven.runtime.storage import RuntimeConfig, identity, write_json
from brain_eleven.runtime.worker import apply_candidate
from brain_eleven.state import StateService


def _candidate(project_id, *, candidate_id, evidence, content):
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


def _source(evidence):
    return {
        "client": "claude",
        "evidence_id": evidence,
        "session_hash": identity("session_", evidence),
        "role": "user",
    }


@pytest.fixture
def b1_runtime_p2(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    project = ProjectRegistry(vault).register(vault, proactive_capture=True)
    StateService(vault).init_project(
        project["project_id"],
        source={"type": "user", "reference": "ig04-b1-p2"},
    )
    migrate(vault)
    write_json(RuntimeConfig(vault).path, {
        "schema_version": 1,
        "mode": "CANARY",
        "project_ids": [project["project_id"]],
        "local_model": None,
        "b1_human_approval": True,
    })
    return vault, project["project_id"]


@pytest.fixture
def b1_two_project_runtime(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    root_a = tmp_path / "project-a"
    root_b = tmp_path / "project-b"
    root_a.mkdir()
    root_b.mkdir()

    registry = ProjectRegistry(vault)
    registry.register(root_a, project_id="project-a", proactive_capture=True)
    registry.register(root_b, project_id="project-b", proactive_capture=True)
    state = StateService(vault)
    state.init_project(
        "project-a", source={"type": "user", "reference": "ig04-b1-p2-a"}
    )
    state.init_project(
        "project-b", source={"type": "user", "reference": "ig04-b1-p2-b"}
    )
    migrate(vault)
    write_json(RuntimeConfig(vault).path, {
        "schema_version": 1,
        "mode": "CANARY",
        "project_ids": ["project-a", "project-b"],
        "local_model": None,
        "b1_human_approval": True,
    })
    return vault


def test_b1_accept_replays_after_crash_after_intent_without_duplicate(
    b1_runtime_p2, monkeypatch
):
    vault, project_id = b1_runtime_p2
    store = ReviewStore(vault)
    evidence = "evd_" + "c" * 32
    candidate = _candidate(
        project_id,
        candidate_id="cand-b1-crash",
        evidence=evidence,
        content="We decided to keep B1 capture crash-safe.",
    )
    review_id = store.add(
        candidate, "HUMAN_APPROVAL_REQUIRED", _source(evidence)
    )
    expected_revision = MemoryStore(vault).revision()

    real_apply_candidate = service_module.apply_candidate

    def crash_before_canonical_write(*args, **kwargs):
        raise RuntimeError("simulated crash after accept intent")

    monkeypatch.setattr(
        service_module, "apply_candidate", crash_before_canonical_write
    )
    with pytest.raises(
        RuntimeError, match="simulated crash after accept intent"
    ):
        review_action(
            vault,
            review_id,
            "accept",
            {"expected_revision": expected_revision},
        )

    interrupted = json.loads(store.path(review_id).read_text(encoding="utf-8"))
    assert interrupted["status"] == "PENDING"
    assert (
        interrupted["accept_intent"]["expected_revision"] == expected_revision
    )
    assert not MemoryStore(vault).load()["validated_memory"]

    monkeypatch.setattr(
        service_module, "apply_candidate", real_apply_candidate
    )
    resumed = review_action(
        vault, review_id, "accept", {"expected_revision": expected_revision}
    )
    assert resumed["status"] == "ACCEPTED"
    assert len(MemoryStore(vault).load()["validated_memory"]) == 1

    replay = review_action(
        vault,
        review_id,
        "accept",
        {"expected_revision": MemoryStore(vault).revision()},
    )
    assert replay["status"] == "ACCEPTED"
    assert len(MemoryStore(vault).load()["validated_memory"]) == 1


def test_b1_accept_stale_revision_keeps_candidate_retryable(b1_runtime_p2):
    vault, project_id = b1_runtime_p2
    store = ReviewStore(vault)
    evidence = "evd_" + "d" * 32
    candidate = _candidate(
        project_id,
        candidate_id="cand-b1-stale",
        evidence=evidence,
        content="We decided to reject stale B1 approvals.",
    )
    review_id = store.add(
        candidate, "HUMAN_APPROVAL_REQUIRED", _source(evidence)
    )
    initial_revision = MemoryStore(vault).revision()

    seed = _candidate(
        project_id,
        candidate_id="cand-b1-seed",
        evidence="evd_" + "e" * 32,
        content="An earlier canonical decision establishes a newer revision.",
    )
    seeded = apply_candidate(
        vault,
        seed,
        op_id=identity("op_", "ig04-b1-p2-seed"),
        approved=True,
        expected_revision=initial_revision,
    )
    assert seeded["status"] == "SUCCESS"
    assert MemoryStore(vault).revision() > initial_revision

    stale = review_action(
        vault, review_id, "accept", {"expected_revision": initial_revision}
    )
    assert stale["status"] in {"CONFLICT", "STALE_INPUT"}
    pending = json.loads(store.path(review_id).read_text(encoding="utf-8"))
    assert pending["status"] == "PENDING"
    assert "accept_intent" not in pending
    assert not any(
        item["content"] == candidate["content"]
        for item in MemoryStore(vault).load()["validated_memory"]
    )

    retry = review_action(
        vault,
        review_id,
        "accept",
        {"expected_revision": MemoryStore(vault).revision()},
    )
    assert retry["status"] == "ACCEPTED"
    matching = [
        item for item in MemoryStore(vault).load()["validated_memory"]
        if item["content"] == candidate["content"]
    ]
    assert len(matching) == 1


def test_b1_rejection_suppression_and_review_visibility_are_project_scoped(
    b1_two_project_runtime,
):
    vault = b1_two_project_runtime
    store = ReviewStore(vault)
    content = "We decided to keep the B1 queue local."
    evidence = "evd_" + "f" * 32

    project_a = store.add(
        _candidate(
            "project-a",
            candidate_id="cand-b1-a",
            evidence=evidence,
            content=content,
        ),
        "HUMAN_APPROVAL_REQUIRED",
        _source(evidence),
    )
    project_b = store.add(
        _candidate(
            "project-b",
            candidate_id="cand-b1-b",
            evidence=evidence,
            content=content,
        ),
        "HUMAN_APPROVAL_REQUIRED",
        _source(evidence),
    )
    assert project_a != project_b

    rejected = review_action(vault, project_a, "reject", {})
    assert rejected["status"] == "REJECTED"

    # A replay in project A is suppressed by its own terminal fingerprint.
    assert store.add(
        _candidate(
            "project-a",
            candidate_id="cand-b1-a-replay",
            evidence=evidence,
            content=content,
        ),
        "HUMAN_APPROVAL_REQUIRED",
        _source(evidence),
    ) == project_a

    # The same content and evidence in project B remains its own pending item.
    assert store.add(
        _candidate(
            "project-b",
            candidate_id="cand-b1-b-replay",
            evidence=evidence,
            content=content,
        ),
        "HUMAN_APPROVAL_REQUIRED",
        _source(evidence),
    ) == project_b

    fingerprint_a = store.fingerprint(
        _candidate(
            "project-a",
            candidate_id="unused-a",
            evidence=evidence,
            content=content,
        )
    )
    fingerprint_b = store.fingerprint(
        _candidate(
            "project-b",
            candidate_id="unused-b",
            evidence=evidence,
            content=content,
        )
    )
    assert fingerprint_a != fingerprint_b
    assert store.find_by_fingerprint("project-a", fingerprint_a) == project_a
    assert store.find_by_fingerprint("project-b", fingerprint_b) == project_b
    assert store.find_by_fingerprint("project-b", fingerprint_a) is None

    visible_pending = [
        item for item in store.list() if item["status"] == "PENDING"
    ]
    assert [item["id"] for item in visible_pending] == [project_b]
    assert visible_pending[0]["project_id"] == "project-b"
    assert all(item["project_id"] != "project-a" for item in visible_pending)
