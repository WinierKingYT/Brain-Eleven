"""Claude Code meta user records are evidence, never the user speaking.

2026-09-30: skill bodies, subagent hand-backs and harness notes arrive as
``type: user`` records with ``isMeta: true``; read as the user's words they
filled the review queue with "committed decisions" such as "Call list_projects
before using project" or "FIXED ...".
"""

from brain_eleven.runtime.evidence import read_increment
from brain_eleven.runtime.extraction import DeterministicExtractor, NewMemoryCandidate
from tests.test_pre13_runtime import _native_path, runtime  # noqa: F401  (fixture)


def _user(text, *, meta=False):
    record = {'type': 'user', 'message': {'role': 'user', 'content': text}}
    if meta:
        record['isMeta'] = True
    return record


def test_meta_user_record_is_system_evidence_and_not_a_memory(runtime, tmp_path):  # noqa: F811
    vault, project = runtime
    path = _native_path(tmp_path, vault, 'claude', 's', [
        _user('Base directory for this skill: we decided to use SQLite for every project.', meta=True),
        _user('We decided to use Postgres for the reporting service.'),
    ])

    batch, _ = read_increment(vault, path, 'claude', 's', project, '2026-09-30T00:00:00Z')

    roles = [(m.record.role, m.content[:12]) for m in batch.messages]
    assert roles == [('system', 'Base directo'), ('user', 'We decided t')]
    memories = [c.content for c in DeterministicExtractor().extract(batch).candidates
                if isinstance(c, NewMemoryCandidate)]
    assert memories == ['We decided to use Postgres for the reporting service.']
