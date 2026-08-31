#!/usr/bin/env python3
"""
scripts/search-api.py integration tests via FastAPI's TestClient.

Every prior verification of this API was manual (curl against a running
uvicorn process) - real, but never captured as an automated test, which
is exactly why search-api.py sat at 0% coverage despite being the most
heavily exercised module in the whole codebase. This file exercises the
actual FastAPI app object end-to-end: real startup/shutdown lifecycle,
real routing, real request/response validation.

vault_path and BRAIN_ELEVEN_API_KEY are both read as module-level globals
at import time (see search-api.py), so each distinct configuration needs
its own fresh module load via importlib - a shared TestClient can't
change them mid-run. Most tests share one module-scoped client pointed
at a seeded temp vault (startup does real work: builds the hybrid search
engine, chat agent, and knowledge graph, so doing this once per file
rather than once per test keeps the suite fast); a separate class loads
the module a second time with an API key set, specifically to test the
auth middleware.
"""

import sys
import os
import json
import importlib.util
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"


def make_memory(**overrides):
    base = {
        "memory_id": "01TESTAPI0000000000000000",
        "source_id": "daily:2026-08-28:observation:0:0",
        "type": "observation",
        "content": "Some memory content",
        "confidence": 0.8,
        "timestamp": "2026-08-28T12:00:00",
        "quality_score": 0.8,
        "status": "active",
        "is_approved": True,
        "superseded_by": "",
    }
    base.update(overrides)
    return base


def write_memories(vault_path, memories):
    claude_dir = vault_path / ".claude"
    claude_dir.mkdir(exist_ok=True)
    with open(claude_dir / "validated-memory.json", "w", encoding="utf-8") as f:
        json.dump({"validated_memory": memories}, f)


def _load_search_api(vault_path, api_key=None):
    """
    Fresh import of search-api.py with VAULT_PATH (and optionally
    BRAIN_ELEVEN_API_KEY) pointed at an isolated vault. Both are read as
    module-level globals at import time, so this must run BEFORE
    importlib executes the module, not after.
    """
    os.environ["VAULT_PATH"] = str(vault_path)
    if api_key is not None:
        os.environ["BRAIN_ELEVEN_API_KEY"] = api_key
    else:
        os.environ.pop("BRAIN_ELEVEN_API_KEY", None)

    # Use a unique module name per load so importlib doesn't reuse a
    # cached module object across differently-configured instances.
    unique_name = f"search_api_test_{id(vault_path)}_{api_key or 'noauth'}"
    spec = importlib.util.spec_from_file_location(unique_name, SCRIPTS_DIR / "search-api.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def vault(tmp_path_factory):
    vault_path = tmp_path_factory.mktemp("search_api_vault")
    write_memories(vault_path, [
        make_memory(memory_id="seed_decision", type="decision",
                    content="Use Redis for caching in this test vault", confidence=0.9,
                    quality_score=0.9),
        make_memory(memory_id="seed_lesson", type="lesson",
                    content="Always write tests before shipping", confidence=0.85,
                    quality_score=0.85),
        make_memory(memory_id="seed_open_loop", type="open_loop",
                    content="Finish the search API test suite", confidence=0.7,
                    quality_score=0.7),
    ])
    return vault_path


@pytest.fixture(scope="module")
def client(vault):
    module = _load_search_api(vault)
    with TestClient(module.app) as c:
        yield c


class TestHealthAndStatus:

    def test_health_returns_200_and_status_healthy(self, client):
        response = client.get("/health")

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "healthy"
        assert "services" in body

    def test_status_returns_memory_count(self, client):
        response = client.get("/status")

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "operational"
        assert body["memory_count"] >= 3  # the 3 seeded memories


class TestSearchRankEmbed:

    def test_search_returns_results_for_seeded_content(self, client):
        response = client.post("/search", json={"query": "Redis caching", "top_k": 3})

        assert response.status_code == 200
        body = response.json()
        assert body["query"] == "Redis caching"
        assert isinstance(body["results"], list)

    def test_search_is_cached_on_repeat_identical_request(self, client):
        first = client.post("/search", json={"query": "unique cache probe query", "top_k": 2})
        assert first.status_code == 200

        stats_before = client.get("/cache/stats").json()
        client.post("/search", json={"query": "unique cache probe query", "top_k": 2})
        stats_after = client.get("/cache/stats").json()

        assert stats_after["l1"]["hits"] > stats_before["l1"]["hits"]

    def test_rank_orders_candidates(self, client):
        response = client.post("/rank", json={
            "query": "Redis",
            "candidates": [{"memory_id": "seed_decision", "combined_score": 0.5}],
        })

        assert response.status_code == 200
        body = response.json()
        assert "results" in body

    def test_embed_returns_vector_with_expected_dimension(self, client):
        response = client.post("/embed", params={"query": "hello world"})

        assert response.status_code == 200
        body = response.json()
        assert body["dimension"] == len(body["embedding"])
        assert body["dimension"] > 0

    def test_embed_is_cached_on_repeat_identical_text(self, client):
        client.post("/embed", params={"query": "cache probe embedding text"})
        stats_before = client.get("/cache/stats").json()
        client.post("/embed", params={"query": "cache probe embedding text"})
        stats_after = client.get("/cache/stats").json()

        assert stats_after["l1"]["hits"] > stats_before["l1"]["hits"]


class TestMemoryCRUD:

    def test_list_memories_returns_seeded_entries(self, client):
        response = client.get("/memories")

        assert response.status_code == 200
        body = response.json()
        ids = {m["memory_id"] for m in body["memories"]}
        assert "seed_decision" in ids

    def test_list_memories_respects_pagination(self, client):
        response = client.get("/memories", params={"skip": 0, "limit": 1})

        assert response.status_code == 200
        assert len(response.json()["memories"]) == 1

    def test_create_memory_goes_through_real_validation(self, client):
        response = client.post("/memories", json={
            "type": "decision", "content": "Adopt PostgreSQL for the test suite", "confidence": 0.75,
            "project": "brain-eleven-tests",
        })

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "created"
        assert len(body["memory_id"]) == 26  # real ULID, not the old fake epoch-based id
        assert body["project"] == "brain-eleven-tests"
        assert "quality_score" in body

    def test_create_memory_with_identical_content_dedupes(self, client):
        first = client.post("/memories", json={
            "type": "lesson", "content": "Dedup probe: identical content test", "confidence": 0.6,
        })
        second = client.post("/memories", json={
            "type": "lesson", "content": "Dedup probe: identical content test", "confidence": 0.6,
        })

        assert second.json()["status"] == "duplicate_returned_existing"
        assert second.json()["memory_id"] == first.json()["memory_id"]

    def test_create_memory_rejects_credential_before_persistence(self, client):
        response = client.post("/memories", json={
            "type": "decision",
            "content": "Authorization: Bearer abcdefghijklmnopqrstuvwxyz012345",
        })

        assert response.status_code == 422
        assert response.json()["detail"] == {
            "accepted": False,
            "reason": "potential_secret",
            "policy": "capture_safety_v1",
        }
        assert all(
            memory["content"] != "Authorization: Bearer abcdefghijklmnopqrstuvwxyz012345"
            for memory in client.get("/memories").json()["memories"]
        )

    def test_get_memory_by_id(self, client):
        response = client.get("/memories/seed_decision")

        assert response.status_code == 200
        assert response.json()["content"] == "Use Redis for caching in this test vault"

    def test_get_memory_missing_id_returns_404(self, client):
        response = client.get("/memories/does-not-exist")

        assert response.status_code == 404

    def test_update_memory_changes_content(self, client):
        created = client.post("/memories", json={
            "type": "observation", "content": "Original content before update", "confidence": 0.6,
        })
        memory_id = created.json()["memory_id"]

        response = client.put(f"/memories/{memory_id}", json={"content": "Updated content after PUT"})

        assert response.status_code == 200
        assert response.json()["content"] == "Updated content after PUT"

    def test_update_memory_rejects_credential_before_persistence(self, client):
        created = client.post("/memories", json={
            "type": "observation", "content": "Safe content before secret update", "confidence": 0.6,
        })
        memory_id = created.json()["memory_id"]

        response = client.put(
            f"/memories/{memory_id}",
            json={"content": "password = hunter2-secret"},
        )

        assert response.status_code == 422
        assert response.json()["detail"]["reason"] == "potential_secret"
        assert client.get(f"/memories/{memory_id}").json()["content"] == "Safe content before secret update"

    def test_update_memory_rejects_stale_expected_revision(self, client):
        created = client.post("/memories", json={
            "type": "observation", "content": "CAS original", "confidence": 0.6,
        })
        memory_id = created.json()["memory_id"]
        revision = client.get("/status").json()["store_revision"]

        updated = client.put(
            f"/memories/{memory_id}",
            json={"content": "CAS first update", "expected_revision": revision},
        )
        assert updated.status_code == 200

        stale = client.put(
            f"/memories/{memory_id}",
            json={"content": "CAS stale update", "expected_revision": revision},
        )
        assert stale.status_code == 409
        assert stale.json()["detail"]["code"] == "MEMORY_STORE_REVISION_CONFLICT"

    def test_update_missing_memory_returns_404(self, client):
        response = client.put("/memories/does-not-exist", json={"content": "irrelevant"})

        assert response.status_code == 404

    def test_delete_memory_soft_deletes(self, client):
        created = client.post("/memories", json={
            "type": "observation", "content": "Content that will be soft-deleted", "confidence": 0.6,
        })
        memory_id = created.json()["memory_id"]

        response = client.delete(f"/memories/{memory_id}")

        assert response.status_code == 200
        assert response.json()["status"] == "deleted"
        assert client.get(f"/memories/{memory_id}").json()["status"] == "deleted"

    def test_delete_missing_memory_returns_404(self, client):
        response = client.delete("/memories/does-not-exist")

        assert response.status_code == 404

    def test_create_memory_triggers_graph_rebuild(self, client):
        stats_before = client.get("/graph/stats").json()

        client.post("/memories", json={
            "type": "decision", "content": "Graph sync probe: adopt Kubernetes for orchestration", "confidence": 0.8,
        })

        stats_after = client.get("/graph/stats").json()
        assert stats_after["total_entities"] > stats_before["total_entities"]


class TestCacheEndpoints:

    def test_cache_stats_returns_l1_and_l3(self, client):
        response = client.get("/cache/stats")

        assert response.status_code == 200
        body = response.json()
        assert "l1" in body
        assert "l3_path" in body

    def test_cache_clear_resets_l1_size(self, client):
        client.post("/search", json={"query": "populate cache before clear", "top_k": 1})

        response = client.post("/cache/clear")

        assert response.status_code == 200
        assert client.get("/cache/stats").json()["l1"]["size"] == 0


class TestGraphEndpoints:

    def test_graph_stats_reflects_seeded_memories(self, client):
        response = client.get("/graph/stats")

        assert response.status_code == 200
        body = response.json()
        assert body["total_entities"] > 0

    def test_graph_entities_filters_by_type(self, client):
        response = client.get("/graph/entities", params={"type": "DECISION"})

        assert response.status_code == 200
        entities = response.json()["entities"]
        assert all(e["type"] == "DECISION" for e in entities)

    def test_graph_entity_relationships(self, client):
        entities = client.get("/graph/entities", params={"type": "DECISION"}).json()["entities"]
        assert entities, "expected at least one DECISION entity from seeded data"
        entity_id = entities[0]["id"]

        response = client.get(f"/graph/entities/{entity_id}/relationships")

        assert response.status_code == 200
        assert response.json()["entity_id"] == entity_id

    def test_graph_relationships_for_missing_entity_returns_404(self, client):
        response = client.get("/graph/entities/does-not-exist/relationships")

        assert response.status_code == 404

    def test_graph_traverse_missing_entity_returns_404(self, client):
        response = client.get("/graph/traverse/does-not-exist")

        assert response.status_code == 404

    def test_graph_traverse_known_entity(self, client):
        entities = client.get("/graph/entities", params={"type": "DECISION"}).json()["entities"]
        entity_id = entities[0]["id"]

        response = client.get(f"/graph/traverse/{entity_id}")

        assert response.status_code == 200
        assert "nodes" in response.json()

    def test_graph_rebuild_returns_fresh_stats(self, client):
        response = client.post("/graph/rebuild")

        assert response.status_code == 200
        assert response.json()["status"] == "rebuilt"


class TestChatEndpoint:

    def test_chat_summarize_intent(self, client):
        response = client.post("/chat", json={"message": "Can you summarize recent decisions?"})

        assert response.status_code == 200
        body = response.json()
        assert body["intent"] == "SUMMARIZE"
        assert body["conversation_id"]

    def test_chat_anomaly_intent(self, client):
        response = client.post("/chat", json={"message": "Are there any anomalies?"})

        assert response.status_code == 200
        assert response.json()["intent"] == "ANOMALY"

    def test_chat_reuses_conversation_id(self, client):
        first = client.post("/chat", json={"message": "Summarize things"})
        conv_id = first.json()["conversation_id"]

        second = client.post("/chat", json={"message": "Anything else?", "conversation_id": conv_id})

        assert second.json()["conversation_id"] == conv_id


class TestMetrics:

    def test_metrics_returns_memory_counts(self, client):
        response = client.get("/metrics")

        assert response.status_code == 200
        body = response.json()
        assert body["memories"]["total"] >= 3


@pytest.fixture(scope="module")
def auth_vault(tmp_path_factory):
    vault_path = tmp_path_factory.mktemp("search_api_auth_vault")
    write_memories(vault_path, [make_memory()])
    return vault_path


@pytest.fixture(scope="module")
def auth_client(auth_vault):
    module = _load_search_api(auth_vault, api_key="test-secret-key")
    with TestClient(module.app) as c:
        yield c
    # Restore a clean env for any tests that run after this module.
    os.environ.pop("BRAIN_ELEVEN_API_KEY", None)


class TestApiKeyAuth:
    """
    Separate module load with BRAIN_ELEVEN_API_KEY actually set - the
    shared `client` fixture above always runs with no key (auth off), so
    this needs its own instance to exercise the require_api_key middleware.
    """

    def test_health_accessible_without_key(self, auth_client):
        response = auth_client.get("/health")

        assert response.status_code == 200

    def test_protected_endpoint_rejects_missing_key(self, auth_client):
        response = auth_client.get("/graph/stats")

        assert response.status_code == 401

    def test_protected_endpoint_rejects_wrong_key(self, auth_client):
        response = auth_client.get("/graph/stats", headers={"X-API-Key": "wrong-key"})

        assert response.status_code == 401

    def test_protected_endpoint_accepts_correct_key(self, auth_client):
        response = auth_client.get("/graph/stats", headers={"X-API-Key": "test-secret-key"})

        assert response.status_code == 200
