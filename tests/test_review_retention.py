"""A person may keep a pending candidate longer, 7 days per click, never past 30 days."""

from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from brain_eleven.runtime.install import _pipeline_health
from brain_eleven.runtime.review import MAX_RETENTION_DAYS, ReviewStore
from brain_eleven.runtime.service import create_app
from brain_eleven.runtime.storage import RuntimeConfig, write_json
from tests.test_memclaim01_claim_key import NEW_TIME, _review_item, _runtime


def _set_times(vault, review_id, created, expires):
    store = ReviewStore(vault)
    raw = next(x for x in store._items() if x["id"] == review_id)
    raw["created_at"], raw["expires_at"] = created.isoformat(), expires.isoformat()
    write_json(store.path(review_id), raw)
    return raw


def test_extend_adds_seven_days_and_caps_at_thirty(tmp_path):
    vault, _ = _runtime(tmp_path, shadow_accept=True)
    item = _review_item(tmp_path, vault, "keep", "We decided that the dashboard stays read-only.", NEW_TIME)
    now = datetime.now(timezone.utc)
    created = now - timedelta(days=6)
    _set_times(vault, item["id"], created, created + timedelta(days=7))

    result = ReviewStore(vault).extend(item["id"])
    assert result["status"] == "EXTENDED"
    new = datetime.fromisoformat(result["expires_at"])
    assert new - (created + timedelta(days=7)) == timedelta(days=7)
    raw = next(x for x in ReviewStore(vault)._items() if x["id"] == item["id"])
    assert raw["kept_by_person"] is True

    cap = created + timedelta(days=MAX_RETENTION_DAYS)
    _set_times(vault, item["id"], created, cap - timedelta(days=2))
    assert datetime.fromisoformat(ReviewStore(vault).extend(item["id"])["expires_at"]) == cap

    client = TestClient(create_app(vault, token="t", background=False), base_url="http://127.0.0.1")
    response = client.post(f"/api/review/candidates/{item['id']}/extend", headers={"Authorization": "Bearer t"}, json={})
    assert response.status_code == 409
    assert "30" in response.json()["detail"]


def test_extend_rejects_non_pending_and_api_extends(tmp_path):
    vault, _ = _runtime(tmp_path, shadow_accept=True)
    item = _review_item(tmp_path, vault, "done", "We decided that SRT-00 is closed.", NEW_TIME)
    now = datetime.now(timezone.utc)
    _set_times(vault, item["id"], now, now + timedelta(days=7))
    client = TestClient(create_app(vault, token="t", background=False), base_url="http://127.0.0.1")
    headers = {"Authorization": "Bearer t"}
    assert client.post(f"/api/review/candidates/{item['id']}/extend", headers=headers, json={}).json()["status"] == "EXTENDED"

    raw = next(x for x in ReviewStore(vault)._items() if x["id"] == item["id"])
    raw["status"] = "REJECTED"
    write_json(ReviewStore(vault).path(item["id"]), raw)
    assert client.post(f"/api/review/candidates/{item['id']}/extend", headers=headers, json={}).status_code == 409


def test_doctor_counts_committed_candidates_expiring_soon(tmp_path):
    vault, _ = _runtime(tmp_path, shadow_accept=True)
    item = _review_item(tmp_path, vault, "soon", "We decided that the dashboard stays read-only.", NEW_TIME)
    now = datetime.now(timezone.utc)
    raw = _set_times(vault, item["id"], now - timedelta(days=6), now + timedelta(hours=10))
    raw["candidate"]["commitment"] = "COMMITTED"
    write_json(ReviewStore(vault).path(item["id"]), raw)

    health = _pipeline_health(vault, RuntimeConfig(vault), tmp_path / "home")
    assert health["review_expiring_committed"] == 1
    assert any("expire within 48h" in s for s in health["suggestions"])
