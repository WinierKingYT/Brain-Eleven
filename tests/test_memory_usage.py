"""Per-memory usage signal (owner decision 2026-09-30)."""

import json

from brain_eleven.runtime.memory_usage import record_delivery, record_use, session_hash, usage
from brain_eleven.runtime.storage import RuntimeConfig
from brain_eleven.runtime.worker import capture_session_key
from tests.test_memclaim01_claim_key import _runtime

AT1, AT2 = '2026-09-30T10:00:00Z', '2026-09-30T10:05:00Z'
CONTENTS = {
    'mem_bandit': 'Bandit gate failure on new checker (subprocess) fixed per repo nosec convention, gate untouched.',
    'mem_sqlite': 'SQLite kullanacağız çünkü uygulama tamamen lokal.',
}


def test_delivery_is_counted_per_memory_and_kind(tmp_path):
    vault, _ = _runtime(tmp_path, shadow_accept=True)
    key = capture_session_key('claude', 'session-1')
    record_delivery(vault, ['mem_bandit', 'mem_sqlite', 'mem_bandit'], session_key=key, event='SessionStart', at=AT1)
    record_delivery(vault, ['mem_bandit'], session_key=key, event='UserPromptSubmit', at=AT2)

    counts = usage(vault)
    assert counts['mem_bandit'] == {'delivered': 2, 'bootstrap_delivered': 1, 'prompt_delivered': 1,
                                    'last_delivered': AT2}
    assert counts['mem_sqlite']['delivered'] == 1


def test_reply_that_draws_on_a_memory_marks_it_used_once_per_session(tmp_path):
    vault, _ = _runtime(tmp_path, shadow_accept=True)
    key = capture_session_key('claude', 'session-1')
    record_delivery(vault, ['mem_bandit', 'mem_sqlite'], session_key=key, event='UserPromptSubmit', at=AT1)
    reply = ('The Bandit gate failure on the new checker (subprocess) was fixed per the repo nosec '
             'convention and the gate stayed untouched.')

    record_use(vault, key, [reply], at=AT2, contents=CONTENTS)
    record_use(vault, key, [reply], at=AT2, contents=CONTENTS)

    counts = usage(vault)
    assert counts['mem_bandit']['used'] == 1 and counts['mem_bandit']['last_used'] == AT2
    assert 'used' not in counts['mem_sqlite']


def test_use_needs_a_delivery_in_the_same_session(tmp_path):
    vault, _ = _runtime(tmp_path, shadow_accept=True)
    record_delivery(vault, ['mem_bandit'], session_key=capture_session_key('claude', 'a'),
                    event='UserPromptSubmit', at=AT1)
    record_use(vault, capture_session_key('claude', 'b'), [CONTENTS['mem_bandit']], at=AT2, contents=CONTENTS)
    assert 'used' not in usage(vault)['mem_bandit']


def test_usage_file_holds_no_text_or_raw_session_ids(tmp_path):
    vault, _ = _runtime(tmp_path, shadow_accept=True)
    key = capture_session_key('claude', 'raw-session-id')
    record_delivery(vault, ['mem_bandit'], session_key=key, event='UserPromptSubmit', at=AT1)
    record_use(vault, key, [CONTENTS['mem_bandit']], at=AT2, contents=CONTENTS)
    raw = (RuntimeConfig(vault).root / 'memory-usage.json').read_text(encoding='utf-8')
    assert 'raw-session-id' not in raw and key not in raw and 'nosec' not in raw
    assert session_hash(key) in json.loads(raw)['sessions']


def test_recording_never_raises(tmp_path, monkeypatch):
    vault, _ = _runtime(tmp_path, shadow_accept=True)
    import brain_eleven.runtime.memory_usage as memory_usage

    def broken(*args, **kwargs):
        raise OSError('disk full')

    monkeypatch.setattr(memory_usage, '_update', broken)
    record_delivery(vault, ['mem_bandit'], session_key='k', event='UserPromptSubmit', at=AT1)
    record_use(vault, 'k', ['text words here'], at=AT2, contents=CONTENTS)
