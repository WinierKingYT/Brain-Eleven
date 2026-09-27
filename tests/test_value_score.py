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
