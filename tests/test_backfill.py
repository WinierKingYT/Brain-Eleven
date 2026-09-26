"""backfill re-runs the extractor on recent transcripts and only ever feeds the review queue."""

import json

from brain_eleven.memory import MemoryStore
from brain_eleven.runtime.backfill import backfill
from brain_eleven.runtime.review import ReviewStore
from brain_eleven.runtime.storage import write_json
from tests.test_pre13_runtime import _native_path, runtime  # noqa: F401  (fixture)

PROPOSAL = "Bundan sonra her PR'da tam test takımını çalıştıracağız."


def _turn(role, text):
    return {'type': role, 'sessionId': 'old', 'message': {'role': role, 'content': text}}


def _claude_home(tmp_path):
    # _native_path writes under tmp_path/<slug>; backfill reads <home>/projects/<slug>.
    return tmp_path.parent / (tmp_path.name + '-home')


def _write(tmp_path, vault, documents):
    home = _claude_home(tmp_path)
    (home / 'projects').mkdir(parents=True, exist_ok=True)
    path = _native_path(home / 'projects', vault, 'claude', 'old', documents)
    return home, path


def test_dry_run_counts_and_apply_adds_review_only(runtime, tmp_path):  # noqa: F811
    vault, _ = runtime
    home, _ = _write(tmp_path, vault, [_turn('assistant', PROPOSAL), _turn('user', 'onaylıyorum'),
                                       _turn('user', 'Karar verildi: holdout ayarını değiştirmeyeceğiz.')])
    memories_before = len(MemoryStore(vault).load()['validated_memory'])

    dry = backfill(vault, claude_home=home, codex_home=tmp_path / 'none')
    assert dry['dry_run'] and dry['transcripts'] == 1 and dry['candidates'] == 2
    assert ReviewStore(vault)._items() == []

    done = backfill(vault, apply=True, claude_home=home, codex_home=tmp_path / 'none')
    assert done['added'] == 2
    contents = sorted(x['candidate']['content'] for x in ReviewStore(vault)._items())
    assert PROPOSAL in contents
    assert all(x['reason'] == 'BACKFILL' for x in ReviewStore(vault)._items())
    assert len(MemoryStore(vault).load()['validated_memory']) == memories_before

    again = backfill(vault, apply=True, claude_home=home, codex_home=tmp_path / 'none')
    assert (again['added'], again['already_pending']) == (0, 2)


def test_rejected_never_returns_and_expired_only_on_request(runtime, tmp_path):  # noqa: F811
    vault, _ = runtime
    home, _ = _write(tmp_path, vault, [_turn('user', 'Karar verildi: holdout ayarını değiştirmeyeceğiz.')])
    backfill(vault, apply=True, claude_home=home, codex_home=tmp_path / 'none')
    store = ReviewStore(vault)
    item = store._items()[0]
    store.finish(item, 'REJECTED')
    again = backfill(vault, apply=True, reoffer_expired=True, claude_home=home, codex_home=tmp_path / 'none')
    assert (again['added'], again['decided_before'], again['reoffered']) == (0, 1, 0)
    assert store._items()[0]['status'] == 'REJECTED'

    raw = store._items()[0]
    raw['status'] = 'EXPIRED'
    write_json(store.path(raw['id']), raw)
    kept = backfill(vault, apply=True, claude_home=home, codex_home=tmp_path / 'none')
    assert kept['decided_before'] == 1 and store._items()[0]['status'] == 'EXPIRED'
    back = backfill(vault, apply=True, reoffer_expired=True, claude_home=home, codex_home=tmp_path / 'none')
    assert back['reoffered'] == 1
    item = store._items()[0]
    assert item['status'] == 'PENDING' and 'holdout' in item['candidate']['content']
    assert 'holdout' not in json.dumps(back)
