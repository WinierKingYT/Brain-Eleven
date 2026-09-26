"""Roadmap step 6: a memory whose source file changed becomes stale_candidate."""

import os
import time
from datetime import datetime

from brain_eleven.memory import MemoryStore
from brain_eleven.runtime import staleness
from tests.test_memclaim01_claim_key import NEW_TIME, _accept, _review_item, _runtime


def _memory_about_file(tmp_path):
    vault, _ = _runtime(tmp_path, shadow_accept=True)
    (vault / "docs").mkdir(exist_ok=True)
    (vault / "docs" / "STATUS.md").write_text("SRT-00 is not ready\n", encoding="utf-8")
    old = datetime.fromisoformat(NEW_TIME.replace("Z", "+00:00")).timestamp() - 86400
    os.utime(vault / "docs" / "STATUS.md", (old, old))
    item = _review_item(tmp_path, vault, "s-file", "We decided that docs/STATUS.md is the release source of truth.", NEW_TIME)
    _accept(vault, item)
    (memory,) = [m for m in MemoryStore(vault).load()["validated_memory"] if "STATUS.md" in m["content"]]
    return vault, memory


def test_referenced_paths_finds_repo_style_names():
    assert staleness.referenced_paths("see `CLAUDE.md` and scripts/worker.py, not v1.2") == ["CLAUDE.md", "scripts/worker.py"]


def test_unchanged_source_is_not_flagged_changed_source_is(tmp_path):
    vault, memory = _memory_about_file(tmp_path)
    assert staleness.scan(vault)["stale_candidates"] == []

    future = time.time() + 3600
    (vault / "docs" / "STATUS.md").write_text("SRT-00 closed\n", encoding="utf-8")
    os.utime(vault / "docs" / "STATUS.md", (future, future))
    (flag,) = staleness.scan(vault)["stale_candidates"]
    assert (flag["memory_id"], flag["path"], flag["reason"]) == (memory["memory_id"], "docs/STATUS.md", "SOURCE_CHANGED")

    staleness.acknowledge(vault, memory["memory_id"], "docs/STATUS.md")
    assert staleness.scan(vault)["stale_candidates"] == []

    later = future + 3600
    os.utime(vault / "docs" / "STATUS.md", (later, later))
    assert len(staleness.scan(vault)["stale_candidates"]) == 1


def test_missing_source_is_flagged_and_retire_resolves_the_memory(tmp_path):
    vault, memory = _memory_about_file(tmp_path)
    (vault / "docs" / "STATUS.md").unlink()
    (flag,) = staleness.scan(vault)["stale_candidates"]
    assert flag["reason"] == "SOURCE_MISSING"

    staleness.retire(vault, memory["memory_id"], "STATUS.md was removed")
    after = next(m for m in MemoryStore(vault).load()["validated_memory"] if m["memory_id"] == memory["memory_id"])
    assert after["status"] == "resolved"
    assert staleness.scan(vault)["stale_candidates"] == []


def test_staleness_api_lists_acks_and_retires(tmp_path):
    from fastapi.testclient import TestClient
    from brain_eleven.runtime.service import create_app

    vault, memory = _memory_about_file(tmp_path)
    future = time.time() + 3600
    os.utime(vault / "docs" / "STATUS.md", (future, future))
    client = TestClient(create_app(vault, token="t", background=False), base_url="http://127.0.0.1")
    headers = {"Authorization": "Bearer t"}
    (flag,) = client.get("/api/staleness", headers=headers).json()["stale_candidates"]
    assert flag["memory_id"] == memory["memory_id"]
    assert client.post(f"/api/staleness/{memory['memory_id']}/retire", headers=headers, json={}).json()["status"] == "RETIRED"
    assert client.get("/api/staleness", headers=headers).json()["stale_candidates"] == []


def test_worker_refreshes_staleness_at_most_once_per_interval(tmp_path, monkeypatch):
    from brain_eleven.runtime import staleness as module
    from brain_eleven.runtime.worker import Worker

    vault, _ = _memory_about_file(tmp_path)
    calls = []
    real = module.scan
    monkeypatch.setattr(module, "scan", lambda v: calls.append(v) or real(v))
    worker = Worker(vault)
    # The capture that created the memory already refreshed the scan.
    assert worker._maybe_scan_staleness() == "SKIPPED_RECENT"
    (vault / ".brain-eleven" / "runtime" / "staleness.json").unlink()
    assert worker._maybe_scan_staleness() == "SCANNED"
    assert worker._maybe_scan_staleness() == "SKIPPED_RECENT"
    assert len(calls) == 1

    monkeypatch.setattr(module, "scan", lambda v: (_ for _ in ()).throw(RuntimeError("boom")))
    (vault / ".brain-eleven" / "runtime" / "staleness.json").unlink()
    assert worker._maybe_scan_staleness() == "DEGRADED"
