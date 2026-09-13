"""Focused W-08D evidence for the typed search API lifecycle boundary."""

import importlib.util
import json
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


SCRIPTS = Path(__file__).parents[1] / "scripts"


def _memory(memory_id, *, scope="global", project_id="", status="active", content=None):
    return {
        "memory_id": memory_id,
        "source_id": f"w08d:{memory_id}",
        "type": "decision",
        "content": content or f"Memory {memory_id}",
        "confidence": 0.8,
        "timestamp": "2026-09-01T12:00:00",
        "quality_score": 0.8,
        "status": status,
        "scope": scope,
        "project": "Project A" if scope == "project" else "",
        "project_id": project_id,
        "is_approved": True,
        "superseded_by": "",
        "dedup_fingerprint": "",
    }


def _write(vault, memories):
    path = vault / ".claude" / "validated-memory.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"validated_memory": memories}), encoding="utf-8")


@pytest.fixture
def api(tmp_path):
    vault = tmp_path / "vault"
    _write(vault, [_memory("source"), _memory("target")])
    os.environ["VAULT_PATH"] = str(vault)
    os.environ.pop("BRAIN_ELEVEN_API_KEY", None)
    name = f"w08d_search_api_{id(vault)}"
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / "search-api.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.app.state.search_api_module = module
    with TestClient(module.app) as client:
        yield module, client, vault


def _document(vault):
    document = json.loads(
        (vault / ".claude" / "validated-memory.json").read_text(encoding="utf-8")
    )
    document.setdefault("revision", 0)
    return document


def test_unknown_status_is_rejected_without_revision_or_graph_effect(api, monkeypatch):
    module, client, vault = api
    before = _document(vault)
    calls = []
    monkeypatch.setattr(module, "_rebuild_graph", lambda: calls.append(True))

    response = client.put("/memories/source", json={"status": "archived"})

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "LIFECYCLE_TRANSITION_INVALID"
    assert _document(vault)["revision"] == before["revision"]
    assert calls == []


def test_resolve_preserves_typed_fields_and_repeated_resolve_is_noop(api, monkeypatch):
    module, client, vault = api
    first = client.put(
        "/memories/source",
        json={"status": "resolved", "resolved_by": "test-run", "reason": "fixed"},
    )
    assert first.status_code == 200
    assert first.json()["status"] == "resolved"
    assert first.json()["resolved_by"] == "test-run"
    assert first.json()["resolution_note"] == "fixed"
    after_first = _document(vault)

    calls = []
    monkeypatch.setattr(module, "_rebuild_graph", lambda: calls.append(True))
    second = client.put("/memories/source", json={"status": "resolved"})

    assert second.status_code == 200
    assert second.json()["store_revision"] == after_first["revision"]
    assert _document(vault)["revision"] == after_first["revision"]
    assert calls == []


def test_supersede_requires_existing_same_scope_target(api):
    _module, client, vault = api
    missing = client.put(
        "/memories/source",
        json={"status": "superseded", "superseded_by": "missing"},
    )
    assert missing.status_code == 422
    assert missing.json()["detail"]["code"] == "LIFECYCLE_TRANSITION_INVALID"
    assert _document(vault)["validated_memory"][0]["status"] == "active"

    accepted = client.put(
        "/memories/source",
        json={
            "status": "superseded",
            "superseded_by": "target",
            "reason": "new decision",
        },
    )
    assert accepted.status_code == 200
    assert accepted.json()["status"] == "superseded"
    assert accepted.json()["superseded_by"] == "target"


def test_terminal_transition_and_delete_through_put_are_rejected(api):
    _module, client, vault = api
    assert client.put(
        "/memories/source", json={"status": "resolved", "resolved_by": "test"}
    ).status_code == 200
    before = _document(vault)["revision"]

    changed = client.put(
        "/memories/source", json={"status": "superseded", "superseded_by": "target"}
    )
    deleted = client.put("/memories/source", json={"status": "deleted"})

    assert changed.status_code == 422
    assert deleted.status_code == 422
    assert _document(vault)["revision"] == before


def test_delete_is_typed_and_repeated_delete_is_noop(api, monkeypatch):
    module, client, vault = api
    first = client.delete("/memories/source")
    assert first.status_code == 200
    first_revision = _document(vault)["revision"]

    calls = []
    monkeypatch.setattr(module, "_rebuild_graph", lambda: calls.append(True))
    second = client.delete("/memories/source")

    assert second.status_code == 200
    assert second.json()["store_revision"] == first_revision
    assert _document(vault)["revision"] == first_revision
    assert calls == []


def test_project_scope_is_required_and_exact_but_global_ignores_request(api):
    module, client, vault = api
    _write(
        vault,
        [
            _memory("global"),
            _memory("project", scope="project", project_id="opaque-a"),
        ],
    )
    # Keep the running graph independent of this direct fixture rewrite.
    module._rebuild_graph()

    required = client.put("/memories/project", json={"content": "new"})
    mismatch = client.put(
        "/memories/project", json={"content": "new", "project_id": "opaque-b"}
    )
    accepted = client.put(
        "/memories/project", json={"content": "new", "project_id": "opaque-a"}
    )
    global_update = client.put(
        "/memories/global", json={"content": "global new", "project_id": "ignored"}
    )

    assert required.json()["detail"]["code"] == "PROJECT_SCOPE_REQUIRED"
    assert mismatch.json()["detail"]["code"] == "PROJECT_SCOPE_MISMATCH"
    assert accepted.status_code == 200
    assert global_update.status_code == 200
    project = next(item for item in _document(vault)["validated_memory"] if item["memory_id"] == "project")
    assert project["project_id"] == "opaque-a"


def test_delete_project_scope_requires_exact_id(api):
    _module, client, vault = api
    _write(vault, [_memory("project", scope="project", project_id="opaque-a")])
    required = client.delete("/memories/project")
    mismatch = client.delete("/memories/project", params={"project_id": "opaque-b"})
    accepted = client.delete("/memories/project", params={"project_id": "opaque-a"})

    assert required.json()["detail"]["code"] == "PROJECT_SCOPE_REQUIRED"
    assert mismatch.json()["detail"]["code"] == "PROJECT_SCOPE_MISMATCH"
    assert accepted.status_code == 200


def test_stale_expected_revision_does_not_write_or_rebuild(api, monkeypatch):
    module, client, vault = api
    revision = _document(vault)["revision"]
    assert client.put("/memories/source", json={"content": "first"}).status_code == 200
    before = _document(vault)
    calls = []
    monkeypatch.setattr(module, "_rebuild_graph", lambda: calls.append(True))

    stale = client.put(
        "/memories/source",
        json={"content": "stale", "expected_revision": revision},
    )

    assert stale.status_code == 409
    assert stale.json()["detail"]["code"] == "MEMORY_STORE_REVISION_CONFLICT"
    assert _document(vault) == before
    assert calls == []


def test_graph_failure_is_visible_after_canonical_commit(api, monkeypatch):
    module, client, vault = api
    monkeypatch.setattr(module, "_rebuild_graph", lambda: (_ for _ in ()).throw(RuntimeError("secret root")))

    response = client.put("/memories/source", json={"content": "committed safely"})

    assert response.status_code == 503
    assert response.json() == {
        "canonical_status": "committed",
        "memory_id": "source",
        "code": "GRAPH_PROJECTION_DEGRADED",
    }
    assert any(
        item["content"] == "committed safely"
        for item in _document(vault)["validated_memory"]
    )


def test_safety_rejection_is_before_canonical_write(api):
    _module, client, vault = api
    before = _document(vault)
    response = client.put(
        "/memories/source",
        json={"content": "Authorization: Bearer abcdefghijklmnopqrstuvwxyz012345"},
    )

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "CAPTURE_SAFETY_REJECTED"
    assert _document(vault) == before


def test_missing_memory_uses_bounded_error(api):
    _module, client, _vault = api
    response = client.put("/memories/missing", json={"content": "safe"})
    assert response.status_code == 404
    assert response.json()["detail"] == {"code": "MEMORY_NOT_FOUND"}
