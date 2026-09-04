"""Phase 16 StateStore schema tests without persistence side effects."""

from __future__ import annotations

import copy
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from state_store import (  # noqa: E402
    MAX_AUDIT_EVENTS,
    STATE_SCHEMA_VERSION,
    StateProvenanceError,
    StateSchemaError,
    empty_state_document,
    new_state_id,
    validate_state_document,
)


NOW = "2026-09-03T12:00:00Z"


def source():
    return {"type": "user", "reference": "user-request"}


def record(prefix, text, status="ACTIVE", **extra):
    return {
        "id": f"{prefix}_01J00000000000000000000000",
        "text": text,
        "status": status,
        "source": source(),
        "created_at": NOW,
        "updated_at": NOW,
        **extra,
    }


def project_state():
    milestone = record("mil", "Phase 16", status="ACTIVE")
    milestone["title"] = milestone.pop("text")
    milestone["phase_id"] = "phase-16"
    objective = record("obj", "Build task and state model", status="ACTIVE")
    return {
        "project_id": "brain-eleven",
        "revision": 0,
        "created_at": NOW,
        "updated_at": NOW,
        "current": {"milestone": milestone, "objective": objective},
        "requirements": [record("req", "Keep state separate from memory")],
        "work_items": [record("wrk", "Define TaskEnvelope", status="TODO")],
        "blockers": [record("blk", "No active blocker", severity="LOW")],
        "constraints": [record("con", "memory_foundation_frozen")],
        "risks": [record("rsk", "Architecture changes need evaluation", severity="MEDIUM")],
        "references": {"memory_ids": ["mem_phase14_frozen"]},
    }


def state_document():
    document = empty_state_document()
    document["updated_at"] = NOW
    document["projects"] = {"brain-eleven": project_state()}
    return document


def test_valid_project_state_document_normalizes_without_changing_authority_fields():
    document = state_document()

    validated = validate_state_document(document)

    assert validated["schema_version"] == STATE_SCHEMA_VERSION
    assert validated["projects"]["brain-eleven"]["current"]["milestone"]["id"].startswith("mil_")
    assert validated["projects"]["brain-eleven"]["references"]["memory_ids"] == ["mem_phase14_frozen"]


def test_schema_rejects_ai_proposed_canonical_state_and_unknown_fields():
    document = state_document()
    document["projects"]["brain-eleven"]["requirements"][0]["source"] = {"type": "ai_proposed"}

    with pytest.raises(StateProvenanceError, match="cannot create canonical"):
        validate_state_document(document)

    document = state_document()
    document["unexpected"] = True
    with pytest.raises(StateSchemaError, match="unknown field"):
        validate_state_document(document)


def test_schema_rejects_secret_text_invalid_revisions_and_too_many_events():
    document = state_document()
    document["projects"]["brain-eleven"]["current"]["objective"]["text"] = "api_key=sk_12345678901234567890"
    with pytest.raises(StateSchemaError, match="credentials or secrets"):
        validate_state_document(document)

    document = state_document()
    document["projects"]["brain-eleven"]["revision"] = -1
    with pytest.raises(StateSchemaError, match="non-negative integer"):
        validate_state_document(document)

    document = state_document()
    document["events"] = [
        {
            "event_id": f"evt_{index:026d}",
            "project_id": "brain-eleven",
            "operation": "test",
            "at": NOW,
            "old_revision": index,
            "new_revision": index + 1,
            "source": source(),
            "record_ids": [],
        }
        for index in range(MAX_AUDIT_EVENTS + 1)
    ]
    with pytest.raises(StateSchemaError, match="must not exceed"):
        validate_state_document(document)


def test_state_ids_are_namespaced_and_unique():
    first = new_state_id("event")
    second = new_state_id("event")
    assert first.startswith("evt_")
    assert first != second
    assert len(first) == len("evt_") + 26
