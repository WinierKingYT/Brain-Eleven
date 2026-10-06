"""Cross-project references at prompt time (owner decision 2026-10-02)."""

from types import SimpleNamespace

import pytest

from brain_eleven.__main__ import main
from brain_eleven.runtime import context as ctx
from brain_eleven.runtime.storage import RuntimeConfig
from tests.test_memclaim01_claim_key import _runtime


class _Embedding:
    provider_id, model = 'stub', 'stub-embed'

    def embed(self, texts):
        # Two dimensions: "backup" words point one way, everything else the other.
        vectors = [[1.0, 0.0] if 'yedek' in text.lower() or 'backup' in text.lower() else [0.0, 1.0] for text in texts]
        return SimpleNamespace(status='EMBEDDING_AVAILABLE', vectors=vectors)


class _Reranker:
    def __init__(self, scores):
        self.scores = scores

    def rerank(self, query, texts):
        return SimpleNamespace(status='EMBEDDING_AVAILABLE', scores=[self.scores.get(t, -6.0) for t in texts])


def _memory(memory_id, project_id, content, kind='decision', status='active'):
    return {'memory_id': memory_id, 'project_id': project_id, 'content': content, 'type': kind,
            'status': status, 'timestamp': '2026-10-01T10:00:00Z'}


MEMORIES = [
    _memory('m1', 'here', 'Bu projenin yedek kararı.'),
    _memory('m2', 'whale', 'Yedek her gün alınıyor ve manifest doğrulanıyor.'),
    _memory('m3', 'whale', 'Yedek hash ok demek doğru içerik demek değil.', kind='lesson'),
    _memory('m4', 'whale', 'Yedek klasörü eski bir gözlem.', kind='observation'),
    _memory('m5', 'whale', 'Yedekten vazgeçildi.', status='resolved'),
    _memory('m6', 'secret', 'Yedek müşterinin sunucusunda tutuluyor.'),
    _memory('m7', 'whale', 'Haber filtresinde tek kelime yanlış pozitif verdi.', kind='lesson'),
    _memory('m8', '', 'Global yedek notu.'),
]


UNRELATED = 'Haber filtresinde tek kelime yanlış pozitif verdi.'


def _related(**extra):
    scores = {m['content']: 3.0 for m in MEMORIES}
    scores[UNRELATED] = -5.0
    scores.update(extra)
    return scores


def _refs(scores, **kw):
    options = dict(project_id='here', private={'secret'}, embedding_provider=_Embedding(),
                   reranker=_Reranker(scores), eligible=lambda memory: True)
    options.update(kw)
    return [m['memory_id'] for m in ctx._cross_project_references('Yedeği nasıl alırım?', MEMORIES, **options)]


def test_only_other_projects_active_decisions_and_lessons_above_the_floor():
    scores = _related(**{'Yedek hash ok demek doğru içerik demek değil.': 1.0})
    # This project, observations, retired, private and global memories never come.
    assert _refs(scores) == ['m2', 'm3']


def test_unrelated_questions_get_nothing_and_the_limit_holds():
    assert _refs({}) == []  # every score -6.0, below the floor
    many = [_memory(f'w{n}', 'whale', f'Yedek kuralı {n}.') for n in range(6)]
    found = ctx._cross_project_references(
        'Yedeği nasıl alırım?', many, project_id='here', private=set(), embedding_provider=_Embedding(),
        reranker=_Reranker({m['content']: 1.0 for m in many}), eligible=lambda memory: True)
    assert len(found) == ctx.CROSS_PROJECT_LIMIT


def test_unsafe_text_and_a_failed_rerank_give_nothing():
    scores = _related()
    assert _refs(scores, eligible=lambda memory: 'manifest' not in memory['content']) == ['m3']

    class Broken:
        def rerank(self, query, texts):
            return SimpleNamespace(status='EMBEDDING_UNAVAILABLE', scores=[])
    assert _refs(scores, reranker=Broken()) == []


def test_references_are_labelled_with_their_source_project():
    text = ctx._format_cross_project([MEMORIES[1]], {'whale': 'whale-tracker'})
    assert text.startswith(ctx.CROSS_PROJECT_HEADING)
    assert '- [whale-tracker, 2026-10] Yedek her gün alınıyor' in text
    assert '[başka proje, 2026-10]' in ctx._format_cross_project([MEMORIES[1]], {})


def test_flag_and_cli(tmp_path):
    vault, project_root = _runtime(tmp_path, shadow_accept=True)
    config = RuntimeConfig(vault)
    assert config.load()['cross_project_recall'] is False and config.load()['cross_project_private'] == []
    with pytest.raises(ValueError):
        config.set_cross_project_recall('yes')
    assert main(['--vault', str(vault), 'cross-project', 'ON']) == 0
    assert config.load()['cross_project_recall'] is True
    assert main(['--vault', str(vault), 'cross-project', 'ON', '--private', 'no-such-project']) == 2
    from brain_eleven.projects.registry import ProjectRegistry
    project = ProjectRegistry(vault).list_projects()[0]
    assert main(['--vault', str(vault), 'cross-project', 'ON', '--private', project['project_label']]) == 0
    assert config.load()['cross_project_private'] == [project['project_id']]


def test_unapproved_memories_of_other_projects_never_come():
    # Review 2026-10-06 (HIGH): the check must see the whole memory, not only its text.
    unapproved = dict(MEMORIES[1], is_approved=False)
    found = ctx._cross_project_references(
        'Yedeği nasıl alırım?', [unapproved, MEMORIES[2]], project_id='here', private=set(),
        embedding_provider=_Embedding(), reranker=_Reranker(_related()),
        eligible=lambda memory: memory.get('is_approved', True) is True)
    assert [m['memory_id'] for m in found] == ['m3']


def test_a_spent_deadline_skips_the_cross_encoder():
    from time import perf_counter
    assert _refs(_related(), deadline=perf_counter() - 1) == []
    assert _refs(_related(), deadline=perf_counter() + 60) == ['m2', 'm3']


@pytest.mark.parametrize(('prompt', 'automated'), [
    ('<task-notification>\n<task-id>b1</task-id>', True),
    ('  <system-reminder>\nCI done', True),
    ('Another Claude session sent a message:\n<agent-message from="a1">', True),
    ('SQLite yedeğini güvenli nasıl alırım?', False),
    ('Bu <task-notification> etiketini neden görüyorum?', False),
    (None, False),
])
def test_harness_turns_are_recognised(prompt, automated):
    # Observed 2026-10-06: notifications pulled tangential references twice.
    assert ctx.is_automated_prompt(prompt) is automated
