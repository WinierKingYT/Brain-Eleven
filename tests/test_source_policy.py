"""Memory source policy (owner decision 2026-09-30).

Session summaries are the main memory source (only their outcome sections);
from the owner's own messages only explicit decisions become memory.
"""

import json

from brain_eleven.runtime.evidence import read_increment
from brain_eleven.runtime.extraction import DeterministicExtractor, NewMemoryCandidate
from tests.test_pre13_runtime import _native_path, runtime  # noqa: F401  (fixture)

NL = "\n"
SUMMARY = NL.join([
    "This session is being continued from a previous conversation.",
    "Summary:",
    "1. Primary Request and Intent:",
    "   - Fix the capture gap and review the branch before merging.",
    "4. Errors and fixes:",
    "   - Bandit gate failure on new checker (subprocess) fixed per repo nosec convention, gate untouched.",
    "     - Detail line joined to its parent bullet.",
    "5. Problem Solving:",
    "   - Solved: W-07B capture-silent-gap (real bug in ownership.py, fixed and pushed).",
    "7. Pending Tasks:",
    "   - Decide the pilot gate and requeue the old dead-letter jobs later.",
    "9. Optional Next Step:",
    "   - Continue the review-finding work in the rtc worktree next session.",
])


def _user(text, **extra):
    return {'type': 'user', 'message': {'role': 'user', 'content': text}, **extra}


def test_summary_is_its_own_source_and_only_outcome_sections_become_candidates(runtime, tmp_path):  # noqa: F811
    vault, project = runtime
    path = _native_path(tmp_path, vault, 'claude', 's', [_user(SUMMARY, isCompactSummary=True)])

    batch, _ = read_increment(vault, path, 'claude', 's', project, '2026-09-30T00:00:00Z')
    assert [m.record.role for m in batch.messages] == ['summary']

    facts = [c.content for c in DeterministicExtractor().extract(batch).candidates
             if isinstance(c, NewMemoryCandidate)]
    assert facts == [
        'Bandit gate failure on new checker (subprocess) fixed per repo nosec convention, gate untouched. '
        'Detail line joined to its parent bullet.',
        'Solved: W-07B capture-silent-gap (real bug in ownership.py, fixed and pushed).',
    ]


def test_owner_messages_keep_only_explicit_decisions_as_memory(runtime, tmp_path):  # noqa: F811
    vault, project = runtime
    path = _native_path(tmp_path, vault, 'claude', 's', [
        _user('Sunucu şu anda eski sürümle çalışıyor.'),
        _user('Bundan sonra deploylari cuma günü yapmayacağız.'),
    ])
    batch, _ = read_increment(vault, path, 'claude', 's', project, '2026-09-30T00:00:00Z')
    result = DeterministicExtractor().extract(batch)

    memories = [c.content for c in result.candidates if isinstance(c, NewMemoryCandidate)]
    assert memories == ['Bundan sonra deploylari cuma günü yapmayacağız.']
    assert 'USER_NOT_DECISION' in {q.reason for q in result.quarantined}


def test_summary_record_stored_as_user_before_the_change_still_persists(runtime, tmp_path):  # noqa: F811
    from dataclasses import replace
    from brain_eleven.runtime.evidence import EvidenceStore

    vault, project = runtime
    path = _native_path(tmp_path, vault, 'claude', 's', [_user(SUMMARY, isCompactSummary=True)])
    batch, _ = read_increment(vault, path, 'claude', 's', project, '2026-09-30T00:00:00Z')
    record = batch.messages[0].record
    store = EvidenceStore(vault)
    store.persist([replace(record, role='user')])
    store.persist([record])  # no EvidenceCorruptError on a replay after the change
    assert json.loads((store.root / (record.evidence_id + '.json')).read_text(encoding='utf-8'))['role'] == 'user'


def test_summary_heading_forms():
    from brain_eleven.runtime.extraction import _legacy
    body = "   - The nightly build was broken on Windows and a retry fixed it."
    for heading in ("4. Errors and fixes:", "## 4. Errors and fixes:", "**4. Errors and fixes:**",
                    "4. **Errors and fixes**:", "4. Hatalar ve düzeltmeler:"):
        assert _legacy.summary_facts("Summary:" + NL + heading + NL + body) == [
            "The nightly build was broken on Windows and a retry fixed it."], heading
