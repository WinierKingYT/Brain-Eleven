"""Focused W-08D evidence for the typed search API lifecycle boundary."""

import importlib.util
import json
import os
import threading
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from brain_eleven.projects.registry import ProjectRegistry


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


def test_put_deleted_is_rejected_even_when_record_is_already_deleted(api):
    _module, client, vault = api
    assert client.delete("/memories/source").status_code == 200
    before = _document(vault)["revision"]

    response = client.put("/memories/source", json={"status": "deleted"})

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "LIFECYCLE_TRANSITION_INVALID"
    assert _document(vault)["revision"] == before


def test_project_scope_is_required_and_exact_but_global_ignores_request(api):
    module, client, vault = api
    _write(
        vault,
        [
            _memory("global"),
            _memory("project", scope="project", project_id="opaque-a"),
        ],
    )
    registry = ProjectRegistry(vault)
    registry.register(vault / "opaque-a", project_id="opaque-a", proactive_capture=True)
    registry.register(vault / "opaque-b", project_id="opaque-b", proactive_capture=True)
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
    registry = ProjectRegistry(vault)
    registry.register(vault / "opaque-a", project_id="opaque-a", proactive_capture=True)
    registry.register(vault / "opaque-b", project_id="opaque-b", proactive_capture=True)
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


def test_concurrent_writer_cas_conflict_does_not_silently_overwrite(api, monkeypatch):
    module, client, vault = api
    expected_revision = _document(vault)["revision"]
    entered = threading.Event()
    writer_done = threading.Event()
    release = threading.Event()
    response_box = {}
    original_transact = module.MemoryStore.transact

    def paused_transact(store, mutator, expected_revision=None):
        if expected_revision == expected_revision_value:
            entered.set()
            assert writer_done.wait(5)
            assert release.wait(5)
        return original_transact(store, mutator, expected_revision=expected_revision)

    expected_revision_value = expected_revision
    monkeypatch.setattr(module.MemoryStore, "transact", paused_transact)
    rebuilds = []
    monkeypatch.setattr(module, "_rebuild_graph", lambda: rebuilds.append(True))

    def update():
        response_box["value"] = client.put(
            "/memories/source",
            json={"content": "must not overwrite writer", "expected_revision": expected_revision},
        )

    update_thread = threading.Thread(target=update)
    update_thread.start()
    assert entered.wait(5)

    module.MemoryStore(vault).append(_memory("writer"))
    writer_done.set()
    release.set()
    update_thread.join(5)

    response = response_box["value"]
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "MEMORY_STORE_REVISION_CONFLICT"
    document = _document(vault)
    assert document["revision"] == expected_revision + 1
    assert {item["memory_id"] for item in document["validated_memory"]} == {"source", "target", "writer"}
    assert next(item for item in document["validated_memory"] if item["memory_id"] == "source")["content"] == "Memory source"
    assert rebuilds == []


def test_canonical_fixture_before_after_preserves_identity_and_scope(api):
    _module, client, vault = api
    before = _document(vault)
    before_by_id = {
        item["memory_id"]: {
            "scope": item.get("scope"),
            "project_id": item.get("project_id", ""),
            "dedup_fingerprint": item.get("dedup_fingerprint", ""),
            "status": item.get("status", "active"),
        }
        for item in before["validated_memory"]
    }
    revision = before["revision"]

    response = client.put(
        "/memories/source",
        json={"status": "resolved", "resolved_by": "fixture-test", "reason": "closed"},
    )

    assert response.status_code == 200
    after = _document(vault)
    assert after["revision"] == revision + 1
    assert {item["memory_id"] for item in after["validated_memory"]} == set(before_by_id)
    after_by_id = {item["memory_id"]: item for item in after["validated_memory"]}
    for memory_id, identity in before_by_id.items():
        assert after_by_id[memory_id]["scope"] == identity["scope"]
        assert after_by_id[memory_id].get("project_id", "") == identity["project_id"]
    assert after_by_id["target"]["status"] == before_by_id["target"]["status"]
    assert after_by_id["source"]["status"] == "resolved"
    assert after_by_id["source"]["resolved_by"] == "fixture-test"
    assert after_by_id["source"]["resolution_note"] == "closed"
    assert after_by_id["source"]["dedup_fingerprint"] != before_by_id["source"]["dedup_fingerprint"]


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


def test_request_validation_does_not_echo_project_paths_or_submitted_values(api):
    _module, client, vault = api
    private_root = str(vault / "private-secret-vault")
    response = client.put(
        "/memories/source",
        json={
            "project_root": private_root,
            "resolved_by": "actor-" + ("x" * 300),
        },
    )

    assert response.status_code == 422
    assert response.json() == {"detail": {"code": "INVALID_REQUEST"}}
    assert private_root not in response.text
    assert "actor-" not in response.text
