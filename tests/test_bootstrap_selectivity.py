"""Roadmap step 9: SessionStart V1 spends its slots on distinct, current facts."""

from brain_eleven.runtime.context import select_distinct


def _m(i, text):
    return {"memory_id": f"mem_{i}", "content": text}


def test_near_duplicates_do_not_take_two_slots():
    ranked = [_m(1, "SRT-00 is closed and shipped with CI green"),
              _m(2, "SRT-00 is closed and shipped, CI green"),
              _m(3, "The holdout gate stays red by decision"),
              _m(4, "Phase 20 remains frozen under IG")]
    chosen = [m["memory_id"] for m in select_distinct(ranked, limit=3)]
    assert chosen == ["mem_1", "mem_3", "mem_4"]


def test_stale_candidates_go_behind_current_memories_but_are_not_dropped():
    ranked = [_m(1, "docs/STATUS.md says SRT-00 is not ready"), _m(2, "Holdout gate stays red"),
              _m(3, "Phase 20 remains frozen")]
    assert [m["memory_id"] for m in select_distinct(ranked, stale_ids={"mem_1"}, limit=2)] == ["mem_2", "mem_3"]
    assert [m["memory_id"] for m in select_distinct(ranked, stale_ids={"mem_1"}, limit=5)] == ["mem_2", "mem_3", "mem_1"]


def test_ranking_order_is_kept_when_nothing_is_redundant():
    ranked = [_m(i, t) for i, t in enumerate(["alpha decision", "beta lesson", "gamma note"])]
    assert select_distinct(ranked, limit=5) == ranked


def test_report_runs_on_a_real_store(tmp_path, capsys):
    import json
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    from bootstrap_selectivity_report import main
    from tests.test_memclaim01_claim_key import NEW_TIME, OLD_TIME, _accept, _review_item, _runtime

    vault, _ = _runtime(tmp_path, shadow_accept=True)
    _accept(vault, _review_item(tmp_path, vault, "a", "We decided that SRT-00 is closed and shipped.", OLD_TIME))
    _accept(vault, _review_item(tmp_path, vault, "b", "We decided SRT-00 is closed and shipped.", NEW_TIME))
    assert main(["--vault", str(vault)]) == 0
    (row,) = json.loads(capsys.readouterr().out).values()
    assert row["old_near_duplicate_slots"] == 1 and row["new_near_duplicate_slots"] == 0
