"""Bulk review cleanup: preview first, reject by filter, nothing deleted."""

from fastapi.testclient import TestClient

from brain_eleven.runtime.review import ReviewStore
from brain_eleven.runtime.service import create_app
from tests.test_memclaim01_claim_key import NEW_TIME, _review_item, _runtime


def test_bulk_reject_previews_then_rejects_only_matching_candidates(tmp_path):
    vault, _ = _runtime(tmp_path, shadow_accept=True)
    keep = _review_item(tmp_path, vault, "keep", "We decided that the dashboard stays read-only.", NEW_TIME)
    noise = _review_item(tmp_path, vault, "noise", "We decided that SRT-00 is closed and shipped.", NEW_TIME)
    client = TestClient(create_app(vault, token="t", background=False), base_url="http://127.0.0.1")
    headers = {"Authorization": "Bearer t"}

    assert client.post("/api/review/bulk-reject", headers=headers, json={}).status_code == 409

    listed = {x["id"]: x for x in client.get("/api/review/candidates", headers=headers).json()["candidates"]}
    assert listed[noise["id"]]["shape"] == "prose"

    # Mark one candidate as the noisy kind, then filter on it.
    store = ReviewStore(vault)
    item = store._items()
    raw = next(x for x in item if x["id"] == noise["id"])
    raw["reason"] = "LOW_EVIDENCE_COMMITMENT"
    from brain_eleven.runtime.storage import write_json
    write_json(store.path(noise["id"]), raw)

    preview = client.post("/api/review/bulk-reject", headers=headers, json={"reason": "LOW_EVIDENCE_COMMITMENT"}).json()
    assert (preview["matched"], preview["dry_run"]) == (1, True)
    assert all(x["status"] == "PENDING" for x in ReviewStore(vault)._items())

    done = client.post("/api/review/bulk-reject", headers=headers,
                       json={"reason": "LOW_EVIDENCE_COMMITMENT", "confirm": True}).json()
    assert (done["matched"], done["dry_run"]) == (1, False)
    by_id = {x["id"]: x for x in ReviewStore(vault)._items()}
    assert by_id[noise["id"]]["status"] == "REJECTED"
    assert by_id[noise["id"]]["decision_note"] == "Toplu ret: reason=LOW_EVIDENCE_COMMITMENT"
    assert by_id[keep["id"]]["status"] == "PENDING"
