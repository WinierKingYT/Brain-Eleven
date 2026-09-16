"""Focused W-25 HTTP scope and authorization boundary coverage."""

import importlib.util
import json
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from brain_eleven.projects.registry import ProjectRegistry


SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"
pytestmark = pytest.mark.integration


def _memory(memory_id, content, *, scope="global", project_id="", project=""):
    return {
        "memory_id": memory_id,
        "source_id": f"daily:2026-09-16:{memory_id}:0:0",
        "type": "observation",
        "content": content,
        "confidence": 0.8,
        "timestamp": "2026-09-16T12:00:00",
        "quality_score": 0.8,
        "status": "active",
        "is_approved": True,
        "superseded_by": "",
        "scope": scope,
        "project": project,
        "project_label": project,
        "project_id": project_id,
    }


def _write_memories(vault, memories):
    claude = vault / ".claude"
    claude.mkdir(parents=True, exist_ok=True)
    (claude / "validated-memory.json").write_text(
        json.dumps({"revision": 0, "validated_memory": memories}),
        encoding="utf-8",
    )


def _load_search_api(vault, *, api_key=None, host=None):
    """Load a fresh app with isolated vault and boundary configuration."""
    names = ("VAULT_PATH", "BRAIN_ELEVEN_API_KEY", "BRAIN_ELEVEN_HOST")
    previous = {name: os.environ.get(name) for name in names}
    present = {name: name in os.environ for name in names}
    try:
        os.environ["VAULT_PATH"] = str(vault)
        if api_key is None:
            os.environ.pop("BRAIN_ELEVEN_API_KEY", None)
        else:
            os.environ["BRAIN_ELEVEN_API_KEY"] = api_key
        if host is None:
            os.environ.pop("BRAIN_ELEVEN_HOST", None)
        else:
            os.environ["BRAIN_ELEVEN_HOST"] = host

        unique_name = f"search_api_w25_{id(vault)}_{api_key or 'noauth'}_{host or 'default'}"
        spec = importlib.util.spec_from_file_location(
            unique_name, SCRIPTS_DIR / "search-api.py"
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        module.app.state.search_api_module = module
        return module
    finally:
        for name in names:
            if present[name]:
                os.environ[name] = previous[name]
            else:
                os.environ.pop(name, None)


@pytest.fixture(scope="module")
def w25_vault(tmp_path_factory):
    vault = tmp_path_factory.mktemp("w25_http_scope")
    registry = ProjectRegistry(vault)
    registry.register(
        vault / "project-a", project_id="project-a", proactive_capture=True
    )
    registry.register(
        vault / "project-b", project_id="project-b", proactive_capture=True
    )
    _write_memories(
        vault,
        [
            _memory("global-memory", "GLOBAL_VISIBLE"),
            _memory(
                "project-a-memory",
                "PROJECT_A_SECRET",
                scope="project",
                project_id="project-a",
                project="Project A",
            ),
            _memory(
                "project-b-memory",
                "PROJECT_B_SECRET",
                scope="project",
                project_id="project-b",
                project="Project B",
            ),
        ],
    )
    return vault


@pytest.fixture(scope="module")
def w25_client(w25_vault):
    module = _load_search_api(w25_vault)
    with TestClient(module.app) as client:
        yield client


@pytest.fixture(scope="module")
def w25_admin_client(w25_vault):
    module = _load_search_api(w25_vault, api_key="w25-admin-key")
    with TestClient(module.app) as client:
        yield client


@pytest.fixture(scope="module")
def w25_configured_key_loopback_client(w25_vault):
    module = _load_search_api(w25_vault, api_key="w25-admin-key")
    with TestClient(module.app) as client:
        yield client


@pytest.fixture(scope="module")
def w25_nonloopback_client(w25_vault):
    module = _load_search_api(w25_vault, host="0.0.0.0")
    with TestClient(module.app) as client:
        yield client


@pytest.fixture(scope="module")
def w25_nonloopback_admin_client(w25_vault):
    module = _load_search_api(
        w25_vault, api_key="w25-admin-key", host="0.0.0.0"
    )
    with TestClient(module.app) as client:
        yield client


def _ids(body, key):
    return {item["memory_id"] for item in body[key]}


def _assert_policy_denial(response, code="HTTP_ADMIN_KEY_REQUIRED"):
    assert response.status_code in {401, 403}
    assert response.json() == {"detail": {"code": code}}
    assert "PROJECT_A_SECRET" not in response.text
    assert "PROJECT_B_SECRET" not in response.text


def _tree_bytes(path):
    if not path.exists():
        return None
    if path.is_file():
        return {"": path.read_bytes()}
    return {
        str(child.relative_to(path)): child.read_bytes()
        for child in sorted(path.rglob("*"))
        if child.is_file()
    }


class TestW25ScopedReads:
    def test_project_context_is_filtered_across_content_routes(self, w25_client):
        listed = w25_client.get(
            "/memories", params={"project_id": "project-a"}
        )
        assert listed.status_code == 200
        assert _ids(listed.json(), "memories") == {
            "global-memory",
            "project-a-memory",
        }

        search = w25_client.post(
            "/search",
            json={
                "query": "PROJECT",
                "top_k": 10,
                "project_id": "project-a",
            },
        )
        assert search.status_code == 200
        assert _ids(search.json(), "results") <= {
            "global-memory",
            "project-a-memory",
        }

        ranked = w25_client.post(
            "/rank",
            json={
                "query": "PROJECT",
                "project_id": "project-a",
                "candidates": [
                    {"memory_id": "global-memory", "combined_score": 0.4},
                    {"memory_id": "project-a-memory", "combined_score": 0.8},
                    {"memory_id": "project-b-memory", "combined_score": 1.0},
                ],
            },
        )
        assert ranked.status_code == 200
        assert _ids(ranked.json(), "results") <= {
            "global-memory",
            "project-a-memory",
        }

        digest = w25_client.get("/digest", params={"project_id": "project-a"})
        assert digest.status_code == 200
        digest_ids = {
            item["memory_id"]
            for items in digest.json()["by_type"].values()
            for item in items
        }
        assert digest_ids == {"global-memory", "project-a-memory"}

        anomalies = w25_client.get(
            "/anomalies", params={"project_id": "project-a"}
        )
        assert anomalies.status_code == 200
        assert anomalies.json()["total_memories_scanned"] == 2
        assert "PROJECT_B_SECRET" not in anomalies.text

        entities = w25_client.get(
            "/graph/entities", params={"project_id": "project-a"}
        )
        assert entities.status_code == 200
        entity_ids = {entity["id"] for entity in entities.json()["entities"]}
        assert "project-a-memory" in entity_ids
        assert "project-b-memory" not in entity_ids
        assert "PROJECT_B_SECRET" not in entities.text

        relationships = w25_client.get(
            "/graph/entities/project-a-memory/relationships",
            params={"project_id": "project-a"},
        )
        assert relationships.status_code == 200
        assert "PROJECT_B_SECRET" not in relationships.text

        traverse = w25_client.get(
            "/graph/traverse/project-a-memory",
            params={"project_id": "project-a"},
        )
        assert traverse.status_code == 200
        assert "project-b-memory" not in traverse.text
        assert "PROJECT_B_SECRET" not in traverse.text

        chat = w25_client.post(
            "/chat",
            json={"message": "summarize", "project_id": "project-a"},
        )
        assert chat.status_code == 200
        assert "PROJECT_B_SECRET" not in chat.text

    def test_default_without_project_is_global_only(self, w25_client):
        listed = w25_client.get("/memories")
        assert listed.status_code == 200
        assert _ids(listed.json(), "memories") == {"global-memory"}
        global_only = w25_client.get(
            "/memories", params={"retrieval_scope": "global"}
        )
        assert _ids(global_only.json(), "memories") == {"global-memory"}

    def test_direct_memory_lookup_obeys_the_same_scope(self, w25_client, w25_admin_client):
        missing_context = w25_client.get("/memories/project-a-memory")
        assert missing_context.status_code == 404
        assert "PROJECT_A_SECRET" not in missing_context.text

        foreign = w25_client.get(
            "/memories/project-b-memory", params={"project_id": "project-a"}
        )
        assert foreign.status_code == 404
        assert "PROJECT_B_SECRET" not in foreign.text

        matching = w25_client.get(
            "/memories/project-a-memory", params={"project_id": "project-a"}
        )
        assert matching.status_code == 200
        assert matching.json()["content"] == "PROJECT_A_SECRET"

        global_record = w25_client.get("/memories/global-memory")
        assert global_record.status_code == 200
        assert global_record.json()["content"] == "GLOBAL_VISIBLE"

        admin = w25_admin_client.get(
            "/memories/project-b-memory",
            params={"retrieval_scope": "all"},
            headers={"X-API-Key": "w25-admin-key"},
        )
        assert admin.status_code == 200
        assert admin.json()["content"] == "PROJECT_B_SECRET"


class TestW25Authorization:
    def test_loopback_scoped_reads_remain_usable_without_admin_key(
        self, w25_configured_key_loopback_client
    ):
        client = w25_configured_key_loopback_client
        scoped = client.get(
            "/memories", params={"project_id": "project-a"}
        )
        assert scoped.status_code == 200
        assert _ids(scoped.json(), "memories") == {
            "global-memory",
            "project-a-memory",
        }

        aggregate = client.get("/graph/stats")
        assert aggregate.status_code == 401
        assert aggregate.json() == {"detail": {"code": "HTTP_ADMIN_KEY_REQUIRED"}}

    @pytest.mark.parametrize(
        "method,path,kwargs",
        [
            ("post", "/search", {"json": {"query": "PROJECT", "retrieval_scope": "all"}}),
            ("post", "/rank", {"json": {"query": "PROJECT", "candidates": [], "retrieval_scope": "all"}}),
            ("get", "/memories", {"params": {"retrieval_scope": "all"}}),
            ("get", "/digest", {"params": {"retrieval_scope": "all"}}),
            ("get", "/anomalies", {"params": {"retrieval_scope": "all"}}),
            ("get", "/graph/entities", {"params": {"retrieval_scope": "all"}}),
            ("get", "/graph/entities/project-a-memory/relationships", {"params": {"retrieval_scope": "all"}}),
            ("get", "/graph/traverse/project-a-memory", {"params": {"retrieval_scope": "all"}}),
            ("post", "/chat", {"json": {"message": "summarize", "retrieval_scope": "all"}}),
        ],
    )
    def test_all_is_admin_only(self, w25_client, method, path, kwargs):
        response = getattr(w25_client, method)(path, **kwargs)
        _assert_policy_denial(response)

    def test_untrusted_admin_parameter_cannot_grant_all(self, w25_client):
        response = w25_client.get(
            "/memories",
            params={"retrieval_scope": "all", "admin": "true"},
            headers={"X-Admin": "true", "X-API-Key": "w25-admin-key"},
        )
        _assert_policy_denial(response)

    def test_admin_key_all_can_read_the_corpus(self, w25_admin_client):
        headers = {"X-API-Key": "w25-admin-key"}
        listed = w25_admin_client.get(
            "/memories", params={"retrieval_scope": "all"}, headers=headers
        )
        assert listed.status_code == 200
        assert _ids(listed.json(), "memories") == {
            "global-memory",
            "project-a-memory",
            "project-b-memory",
        }

        searched = w25_admin_client.post(
            "/search",
            json={"query": "PROJECT", "retrieval_scope": "all"},
            headers=headers,
        )
        assert searched.status_code == 200
        assert _ids(searched.json(), "results") <= {
            "global-memory",
            "project-a-memory",
            "project-b-memory",
        }

        anomalies = w25_admin_client.get(
            "/anomalies", params={"retrieval_scope": "all"}, headers=headers
        )
        assert anomalies.status_code == 200
        assert anomalies.json()["total_memories_scanned"] == 3

    def test_missing_and_wrong_keys_are_bounded(self, w25_admin_client):
        missing = w25_admin_client.get(
            "/memories", params={"retrieval_scope": "all"}
        )
        _assert_policy_denial(missing)
        wrong = w25_admin_client.get(
            "/memories",
            params={"retrieval_scope": "all"},
            headers={"X-API-Key": "wrong-key"},
        )
        _assert_policy_denial(wrong)

    def test_registry_unknown_archived_disabled_and_corrupt_fail_closed(
        self, w25_client, w25_vault
    ):
        unknown = w25_client.get(
            "/memories", params={"project_id": "unknown-project"}
        )
        assert unknown.status_code == 404
        assert unknown.json() == {"detail": {"code": "HTTP_PROJECT_UNKNOWN"}}
        assert "unknown-project" not in unknown.text

        registry = ProjectRegistry(w25_vault)
        root_archived = w25_vault / "archived"
        root_disabled = w25_vault / "disabled"
        registry.register(root_archived, project_id="project-archived", proactive_capture=True)
        registry.register(root_disabled, project_id="project-disabled", proactive_capture=False)
        registry.set_status("project-archived", "archived")
        try:
            archived = w25_client.get(
                "/memories", params={"project_id": "project-archived"}
            )
            disabled = w25_client.get(
                "/memories", params={"project_id": "project-disabled"}
            )
            assert archived.json() == {"detail": {"code": "HTTP_PROJECT_UNAVAILABLE"}}
            assert disabled.json() == {"detail": {"code": "HTTP_PROJECT_UNAVAILABLE"}}
            assert archived.status_code == disabled.status_code == 403
        finally:
            registry.set_status("project-archived", "active")

        registry_file = w25_vault / ".claude" / "project-registry.json"
        original = registry_file.read_bytes()
        try:
            registry_file.write_text("not-json", encoding="utf-8")
            corrupt = w25_client.get(
                "/memories", params={"project_id": "project-a"}
            )
            assert corrupt.status_code == 404
            assert corrupt.json() == {"detail": {"code": "HTTP_PROJECT_UNKNOWN"}}
        finally:
            registry_file.write_bytes(original)

    def test_malformed_scope_inputs_are_bounded(self, w25_client):
        required = w25_client.get(
            "/memories", params={"retrieval_scope": "project"}
        )
        assert required.status_code == 403
        assert required.json() == {"detail": {"code": "HTTP_SCOPE_REQUIRED"}}

        invalid = w25_client.get(
            "/memories", params={"project_id": "../PROJECT_B_SECRET"}
        )
        assert invalid.status_code == 422
        assert invalid.json() == {"detail": {"code": "HTTP_PROJECT_INVALID"}}
        assert "PROJECT_B_SECRET" not in invalid.text

    def test_unauthorized_project_mutations_are_read_only(self, w25_client, w25_vault):
        memory_file = w25_vault / ".claude" / "validated-memory.json"
        before = memory_file.read_bytes()
        unknown = "unknown-project"

        create = w25_client.post(
            "/memories",
            json={
                "type": "observation",
                "content": "must not be stored",
                "scope": "project",
                "project_id": unknown,
            },
        )
        update = w25_client.put(
            "/memories/project-a-memory",
            json={"content": "must not be updated", "project_id": unknown},
        )
        delete = w25_client.delete(
            "/memories/project-a-memory", params={"project_id": unknown}
        )

        assert create.status_code == 404
        assert update.status_code == 404
        assert delete.status_code == 404
        assert create.json() == update.json() == delete.json() == {
            "detail": {"code": "HTTP_PROJECT_UNKNOWN"}
        }
        assert memory_file.read_bytes() == before


class TestW25RouteMatrix:
    def test_non_loopback_without_key_fails_closed_but_health_is_public(
        self, w25_nonloopback_client
    ):
        assert w25_nonloopback_client.get("/health").status_code == 200
        for method, path, kwargs in [
            ("get", "/status", {}),
            ("get", "/metrics", {}),
            ("get", "/cache/stats", {}),
            ("get", "/graph/stats", {}),
            ("get", "/memories", {}),
            ("post", "/embed", {"params": {"query": "hello"}}),
            ("post", "/cache/clear", {}),
            ("post", "/graph/rebuild", {}),
        ]:
            response = getattr(w25_nonloopback_client, method)(path, **kwargs)
            _assert_policy_denial(response)

    def test_non_loopback_admin_key_allows_protected_routes(
        self, w25_nonloopback_admin_client
    ):
        headers = {"X-API-Key": "w25-admin-key"}
        assert w25_nonloopback_admin_client.get("/status", headers=headers).status_code == 200
        assert w25_nonloopback_admin_client.get("/metrics", headers=headers).status_code == 200
        assert w25_nonloopback_admin_client.get("/cache/stats", headers=headers).status_code == 200
        assert w25_nonloopback_admin_client.get("/graph/stats", headers=headers).status_code == 200
        all_memories = w25_nonloopback_admin_client.get(
            "/memories", params={"retrieval_scope": "all"}, headers=headers
        )
        assert all_memories.status_code == 200

    def test_denied_reads_do_not_change_canonical_or_derived_bytes(
        self, w25_client, w25_vault
    ):
        module = w25_client.app.state.search_api_module
        status_before = w25_client.get("/status").json()["store_revision"]
        tracked = [
            w25_vault / ".claude" / "validated-memory.json",
            w25_vault / ".claude" / "validated-memory.backup.json",
            w25_vault / ".claude" / "knowledge-graph.json",
            w25_vault / ".claude" / "knowledge-graph.backup.json",
        ]
        before = {path: path.read_bytes() if path.exists() else None for path in tracked}
        cache_stats_before = module.cache.stats()
        l3_path = Path(cache_stats_before["l3_path"])
        l3_before = _tree_bytes(l3_path)

        _assert_policy_denial(
            w25_client.post(
                "/search", json={"query": "PROJECT", "retrieval_scope": "all"}
            )
        )
        _assert_policy_denial(
            w25_client.get("/anomalies", params={"retrieval_scope": "all"})
        )
        _assert_policy_denial(
            w25_client.post(
                "/chat", json={"message": "summarize", "retrieval_scope": "all"}
            )
        )

        assert w25_client.get("/status").json()["store_revision"] == status_before
        assert {path: path.read_bytes() if path.exists() else None for path in tracked} == before
        assert _tree_bytes(l3_path) == l3_before
        assert module.cache.stats()["l1"]["size"] == cache_stats_before["l1"]["size"]

    @pytest.mark.parametrize(
        "host,expected",
        [
            ("127.0.0.1", True),
            ("::1", True),
            ("localhost", True),
            ("LOCALHOST", True),
            ("0.0.0.0", False),
            ("::", False),
            ("127.0.0.2", False),
            ("localhost ", False),
            ("", False),
        ],
    )
    def test_host_policy_uses_exact_loopback_values(
        self, w25_vault, host, expected
    ):
        module = _load_search_api(w25_vault, host=host)
        assert module._IS_LOOPBACK_HOST is expected
