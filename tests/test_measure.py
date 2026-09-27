"""One-command measurement snapshot over a real runtime vault."""

import json

from brain_eleven.runtime.measure import measure
from brain_eleven.runtime.storage import RuntimeConfig, write_json
from tests.test_memclaim01_claim_key import NEW_TIME, OLD_TIME, _accept, _review_item, _runtime


def test_measure_combines_all_reports_and_saves_a_snapshot(tmp_path):
    vault, _ = _runtime(tmp_path, shadow_accept=True)
    _accept(vault, _review_item(tmp_path, vault, "a", "We decided that SRT-00 is closed and shipped.", OLD_TIME))
    _review_item(tmp_path, vault, "b", "We decided that the dashboard stays read-only.", NEW_TIME)
    write_json(RuntimeConfig(vault).root / "installation.json",
               {"clients": {"codex": {"installed_at": "2000-01-01T00:00:00+00:00"}}})

    result = measure(vault, claude_home=tmp_path / "claude-home", codex_home=tmp_path / "codex-home")

    assert result["since"] == "2000-01-01T00:00:00+00:00"
    assert result["capture"]["verdict"] == "INSUFFICIENT_EVIDENCE"
    assert result["review_noise"]["total"] == 2
    assert set(result) >= {"capture", "review_noise", "staleness", "bootstrap"}
    saved = json.loads(open(result["saved_to"], encoding="utf-8").read())
    assert saved["review_noise"] == result["review_noise"]
    assert "SRT-00" not in json.dumps(result)


def test_provenance_separates_captured_backfill_and_remember(tmp_path):
    from brain_eleven.memory import MemoryStore
    from brain_eleven.runtime.measure import provenance
    from brain_eleven.runtime.review import ReviewStore
    from brain_eleven.runtime.storage import write_json
    from tests.test_memclaim01_claim_key import NEW_TIME, _accept, _review_item, _runtime
    vault, _ = _runtime(tmp_path, shadow_accept=True)
    _accept(vault, _review_item(tmp_path, vault, "a", "We decided the dashboard stays read-only.", NEW_TIME))
    b = _review_item(tmp_path, vault, "b", "We decided to keep SQLite for storage.", NEW_TIME)
    raw = next(x for x in ReviewStore(vault)._items() if x["id"] == b["id"])
    raw["reason"] = "BACKFILL"
    write_json(ReviewStore(vault).path(b["id"]), raw)
    _accept(vault, b)
    document = MemoryStore(vault).load()
    before = provenance(vault)
    assert before["active"].get("captured_accepted") == 1 and before["active"].get("backfill_accepted") == 1
    assert "dashboard" not in str(before)
    assert set(before) == {"active", "since"} and len(document["validated_memory"]) >= 2
