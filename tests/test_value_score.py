"""Layer-2 value score: decisions, novelty and recall answers rank first."""

from fastapi.testclient import TestClient

from brain_eleven.runtime.service import create_app
from brain_eleven.runtime.value import DAILY_LIMIT, value_score
from tests.test_memclaim01_claim_key import NEW_TIME, _review_item, _runtime


def _item(content, commitment, memory_type, similar=0.0, recall=None):
    return {'candidate': {'candidate_type': 'NEW_MEMORY', 'content': content, 'commitment': commitment,
                          'memory_type': memory_type},
            'similar': [{'similarity': similar}] if similar else [], 'recall_questions': recall or []}


SENTENCE = "Bundan sonra her PR'da tam test takımını çalıştıracağız, CI tek başına yetmez."


def test_committed_new_decision_outranks_observation_and_duplicate():
    decision = value_score(_item(SENTENCE, 'COMMITTED', 'decision'))
    observation = value_score(_item(SENTENCE, 'OBSERVED', 'observation'))
    duplicate = value_score(_item(SENTENCE, 'COMMITTED', 'decision', similar=0.8))
    fragment = value_score(_item('kısa not', 'COMMITTED', 'decision'))
    assert decision > observation and decision > duplicate and decision > fragment
    assert value_score(_item('x' * 50, 'OBSERVED', 'observation', recall=[3])) > decision


def test_candidates_api_returns_score_and_daily_limit(tmp_path):
    vault, _ = _runtime(tmp_path, shadow_accept=True)
    _review_item(tmp_path, vault, "a", "We decided the dashboard stays read-only.", NEW_TIME)
    client = TestClient(create_app(vault, token="t", background=False), base_url="http://127.0.0.1")
    body = client.get("/api/review/candidates", headers={"Authorization": "Bearer t"}).json()
    assert body["daily_limit"] == DAILY_LIMIT
    assert all(isinstance(x["value_score"], float) for x in body["candidates"] if x["status"] == "PENDING")


def test_accept_many_accepts_each_through_the_normal_path(tmp_path):
    from brain_eleven.memory import MemoryStore
    from brain_eleven.runtime.review import ReviewStore
    vault, _ = _runtime(tmp_path, shadow_accept=True)
    a = _review_item(tmp_path, vault, "a", "We decided the dashboard stays read-only.", NEW_TIME)
    b = _review_item(tmp_path, vault, "b", "We decided to keep SQLite for storage.", NEW_TIME)
    client = TestClient(create_app(vault, token="t", background=False), base_url="http://127.0.0.1")
    headers = {"Authorization": "Bearer t"}
    assert client.post("/api/review/accept-many", headers=headers, json={"ids": []}).status_code == 409
    result = client.post("/api/review/accept-many", headers=headers, json={"ids": [a["id"], b["id"], "bad"]}).json()
    assert result["accepted"] == 2 and result["results"]["bad"].startswith("FAILED")
    contents = {m["content"] for m in MemoryStore(vault).load()["validated_memory"]}
    assert {"We decided the dashboard stays read-only.", "We decided to keep SQLite for storage."} <= contents
    assert {x["id"]: x["status"] for x in ReviewStore(vault)._items()}[a["id"]] == "ACCEPTED"


def test_digest_lists_the_top_candidates(tmp_path):
    from brain_eleven.runtime.value import digest
    vault, _ = _runtime(tmp_path, shadow_accept=True)
    _review_item(tmp_path, vault, "a", "We decided the dashboard stays read-only.", NEW_TIME)
    result = digest(vault)
    assert result["pending"] == 1 and result["top"][0]["text"].startswith("We decided")
