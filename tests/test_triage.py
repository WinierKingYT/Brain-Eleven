"""Layer-1 automatic noise filter: noise never reaches the queue, decisions always do."""

from brain_eleven.runtime.review import ReviewStore
from brain_eleven.runtime.storage import RuntimeConfig, write_json
from brain_eleven.runtime.triage import noise_rule, summary, triage_existing
from brain_eleven.runtime.worker import Worker, enqueue
from tests.test_memclaim01_claim_key import NEW_TIME, _review_item, _runtime


def _candidate(content, commitment, memory_type='observation'):
    return {'candidate_type': 'NEW_MEMORY', 'content': content, 'commitment': commitment, 'memory_type': memory_type}


def test_rules_match_noise_and_never_a_committed_decision():
    assert noise_rule(_candidate('"alıntı" dedi ki bu böyle', 'QUOTED'), 'REVIEW_REQUIRED') == 'QUOTED'
    assert noise_rule(_candidate('tamam', 'UNCERTAIN'), 'LOW_EVIDENCE_COMMITMENT') == 'SHORT_ACK'
    assert noise_rule(_candidate('Burada bir şeyler oluyor gibi görünüyor sanki.', 'UNCERTAIN'),
                      'LOW_EVIDENCE_COMMITMENT') == 'LOW_EVIDENCE_PROSE'
    assert noise_rule(_candidate('$ git status\n$ git log', 'OBSERVED'), 'LOW_EVIDENCE_COMMITMENT') == 'LOW_EVIDENCE_CODE'
    decision = _candidate('tamam', 'COMMITTED', 'decision')
    assert noise_rule(decision, 'LOW_EVIDENCE_COMMITMENT') is None
    assert noise_rule(_candidate('We decided the dashboard stays read-only.', 'COMMITTED', 'decision'),
                      'REVIEW_REQUIRED') is None


def test_worker_counts_noise_instead_of_queueing_it(tmp_path):
    vault, _ = _runtime(tmp_path, shadow_accept=True)
    keep = _review_item(tmp_path, vault, "keep", "We decided the dashboard stays read-only.", NEW_TIME)
    assert keep["status"] == "PENDING"
    before = len(ReviewStore(vault)._items())
    worker = Worker(vault)
    assert worker._add_review(_candidate('tamam', 'UNCERTAIN') | {'candidate_id': 'cand_x', 'project_id': keep['project_id']},
                              'LOW_EVIDENCE_COMMITMENT', {'client': 'claude'}) is None
    assert len(ReviewStore(vault)._items()) == before
    assert summary(vault)['by_rule'] == {'SHORT_ACK': 1} and 'tamam' not in str(summary(vault))

    cfg = RuntimeConfig(vault)
    write_json(cfg.path, {**cfg.load(), 'auto_triage': False})
    assert worker._add_review(_candidate('tamam', 'UNCERTAIN') | {'candidate_id': 'cand_y', 'project_id': keep['project_id']},
                              'LOW_EVIDENCE_COMMITMENT', {'client': 'claude'}) is not None


def test_triage_existing_previews_then_rejects_only_noise(tmp_path):
    vault, _ = _runtime(tmp_path, shadow_accept=True)
    keep = _review_item(tmp_path, vault, "keep", "We decided the dashboard stays read-only.", NEW_TIME)
    noise = _review_item(tmp_path, vault, "noise", "We decided that SRT-00 is closed and shipped.", NEW_TIME)
    store = ReviewStore(vault)
    raw = next(x for x in store._items() if x["id"] == noise["id"])
    raw["candidate"]["commitment"] = "QUOTED"
    write_json(store.path(noise["id"]), raw)

    preview = triage_existing(vault)
    assert preview["dry_run"] and preview["matched"] == 1
    assert all(x["status"] == "PENDING" for x in store._items())
    done = triage_existing(vault, apply=True)
    assert done["by_rule"]["QUOTED"] == 1
    by_id = {x["id"]: x for x in store._items()}
    assert by_id[noise["id"]]["status"] == "REJECTED"
    assert by_id[noise["id"]]["decision_note"] == "Otomatik süzgeç: QUOTED"
    assert by_id[keep["id"]]["status"] == "PENDING"
