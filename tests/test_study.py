"""Study a project or GitHub repo for decisions and lessons (owner decision 2026-10-06)."""

import json
import shutil
import subprocess

import pytest

from brain_eleven.__main__ import main
from brain_eleven.memory import MemoryStore
from brain_eleven.runtime import study
from brain_eleven.runtime.storage import RuntimeConfig
from tests.test_memclaim01_claim_key import _runtime

pytestmark = pytest.mark.skipif(shutil.which('git') is None, reason='git not installed')
ITEM = {'type': 'decision', 'text': 'Depolama için tek dosyalı SQLite seçildi, çünkü veri hacmi küçük.',
        'source': 'docs/PLAN.md'}


def _git(root, *args):
    subprocess.run(['git', '-C', str(root), *args], check=True, capture_output=True)


def _repo(path):
    path.mkdir(parents=True)
    _git(path, 'init', '-q')
    _git(path, 'config', 'user.email', 't@example.com')
    _git(path, 'config', 'user.name', 't')
    (path / 'README.md').write_text('# demo\n', encoding='utf-8')
    _git(path, 'add', '.')
    _git(path, 'commit', '-qm', 'init')
    return path


def _head(root):
    return subprocess.run(['git', '-C', str(root), 'rev-parse', 'HEAD'], check=True, capture_output=True,
                          text=True).stdout.strip()


def _memories(vault, project_id):
    return [m for m in MemoryStore(vault).load()['validated_memory'] if m.get('project_id') == project_id]


def test_full_then_up_to_date_then_incremental(tmp_path):
    vault, _ = _runtime(tmp_path, shadow_accept=True)
    repo = _repo(tmp_path / 'proj')
    project = RuntimeConfig(vault).enroll_project(repo)

    first = study.status(vault, repo)
    assert first['mode'] == 'FULL' and first['head'] == _head(repo)
    result = study.write(vault, repo, [ITEM], commit=first['head'])
    assert result['written'] == 1
    [memory] = _memories(vault, project['project_id'])
    assert memory['content'].endswith(f"(kaynak: {project['project_label']} docs/PLAN.md)")
    assert study.status(vault, repo)['mode'] == 'UP_TO_DATE'

    (repo / 'docs').mkdir()
    (repo / 'docs' / 'PLAN.md').write_text('Karar: Postgres.\n', encoding='utf-8')
    (repo / 'app.py').write_text('print(1)\n', encoding='utf-8')
    _git(repo, 'add', '.')
    _git(repo, 'commit', '-qm', 'switch storage')
    later = study.status(vault, repo)
    assert later['mode'] == 'INCREMENTAL'
    assert later['changed_docs'] == ['docs/PLAN.md'] and later['changed_files'] == 2
    assert len(later['commits']) == 1 and 'switch storage' in later['commits'][0]

    study.mark(vault, repo, commit=later['head'])
    assert study.status(vault, repo)['mode'] == 'UP_TO_DATE'


def test_a_sub_folder_belongs_to_its_enrolled_project_and_unknown_folders_fail(tmp_path):
    vault, _ = _runtime(tmp_path, shadow_accept=True)
    outer = tmp_path / 'vault-folder'
    inner = _repo(outer / 'inner')
    project = RuntimeConfig(vault).enroll_project(outer)
    assert study.resolve_target(vault, inner)['project_id'] == project['project_id']
    assert study.status(vault, inner)['head'] == _head(inner)
    with pytest.raises(ValueError):
        study.resolve_target(vault, _repo(tmp_path / 'stranger'))


def test_github_target_is_an_external_project_without_capture(tmp_path):
    vault, _ = _runtime(tmp_path, shadow_accept=True)
    info = study.resolve_target(vault, 'https://github.com/Acme/Widget.git')
    assert info['label'] == 'ext:acme/widget' and info['external'] is True
    assert info['root'].parent == RuntimeConfig(vault).root / study.CACHE_DIR
    _repo(info['root'])  # stands in for the clone; no network in tests

    result = study.write(vault, 'https://github.com/Acme/Widget', [ITEM], commit=_head(info['root']))
    assert result['written'] == 1
    assert result['project_id'] not in RuntimeConfig(vault).load()['project_ids']
    assert study.status(vault, 'https://github.com/acme/widget', sync=False)['mode'] == 'UP_TO_DATE'


@pytest.mark.parametrize('items', [[], [{'type': 'plan', 'text': 'x', 'source': 'a'}],
                                   [{'type': 'lesson', 'text': '', 'source': 'a'}],
                                   [{'type': 'lesson', 'text': 'x' * 1201, 'source': 'a'}],
                                   [{'type': 'lesson', 'text': 'ok text', 'source': ''}]])
def test_invalid_items_are_rejected(tmp_path, items):
    vault, _ = _runtime(tmp_path, shadow_accept=True)
    repo = _repo(tmp_path / 'proj')
    RuntimeConfig(vault).enroll_project(repo)
    with pytest.raises(ValueError):
        study.write(vault, repo, items)


def test_cli_status_write_and_mark(tmp_path, capsys):
    vault, _ = _runtime(tmp_path, shadow_accept=True)
    repo = _repo(tmp_path / 'proj')
    RuntimeConfig(vault).enroll_project(repo)
    items = tmp_path / 'items.json'
    items.write_text(json.dumps([ITEM], ensure_ascii=False), encoding='utf-8')
    assert main(['--vault', str(vault), 'study', 'status', str(repo)]) == 0
    assert main(['--vault', str(vault), 'study', 'write', str(repo), '--items', str(items),
                 '--commit', _head(repo)]) == 0
    assert main(['--vault', str(vault), 'study', 'write', str(repo)]) == 2
    assert main(['--vault', str(vault), 'study', 'mark', str(repo)]) == 2
    capsys.readouterr()
    assert main(['--vault', str(vault), 'study', 'status', str(repo)]) == 0
    assert json.loads(capsys.readouterr().out)['mode'] == 'UP_TO_DATE'


def test_a_failed_item_leaves_the_study_unrecorded(tmp_path, monkeypatch):
    # Review 2026-10-06 (HIGH): a rejected item must be studied again next time.
    vault, _ = _runtime(tmp_path, shadow_accept=True)
    repo = _repo(tmp_path / 'proj')
    RuntimeConfig(vault).enroll_project(repo)
    monkeypatch.setattr('brain_eleven.memory.capture.remember', lambda *a, **k: {'accepted': False, 'reason': 'SECRET'})
    result = study.write(vault, repo, [ITEM], commit=_head(repo))
    assert result['written'] == 0 and result['failed'] == ['docs/PLAN.md'] and result['recorded'] is False
    assert study.status(vault, repo)['mode'] == 'FULL'


@pytest.mark.parametrize('commit', ['HEAD', 'abc', '--output=x', 'g' * 40])
def test_commit_must_be_a_full_id(tmp_path, commit):
    vault, _ = _runtime(tmp_path, shadow_accept=True)
    repo = _repo(tmp_path / 'proj')
    RuntimeConfig(vault).enroll_project(repo)
    with pytest.raises(ValueError):
        study.mark(vault, repo, commit=commit)
    with pytest.raises(ValueError):
        study.write(vault, repo, [ITEM], commit=commit)


@pytest.mark.parametrize('url', ['https://github.com/a/..', 'https://github.com/-x/repo', 'https://github.com/a/b.',
                                 'https://github.com/a/b/../c', 'https://gitlab.com/a/b', 'file:///c/repo'])
def test_bad_repository_names_are_rejected(tmp_path, url):
    vault, _ = _runtime(tmp_path, shadow_accept=True)
    with pytest.raises(ValueError):
        study.resolve_target(vault, url)


def test_sub_folder_write_is_saved_under_the_enrolled_project(tmp_path):
    vault, _ = _runtime(tmp_path, shadow_accept=True)
    outer = tmp_path / 'vault-folder'
    inner = _repo(outer / 'inner')
    project = RuntimeConfig(vault).enroll_project(outer)
    from pathlib import Path
    assert Path(study.status(vault, inner)['project_root']) == outer.resolve()
    assert study.write(vault, inner, [ITEM], commit=_head(inner))['written'] == 1
    assert len(_memories(vault, project['project_id'])) == 1


def test_a_repositorys_own_config_cannot_run_commands(tmp_path):
    # Review 2026-10-06: an enrolled folder may carry a hostile .git/config.
    vault, _ = _runtime(tmp_path, shadow_accept=True)
    repo = _repo(tmp_path / 'proj')
    RuntimeConfig(vault).enroll_project(repo)
    study.mark(vault, repo, commit=_head(repo))
    marker = tmp_path / 'pwned'
    _git(repo, 'config', 'core.fsmonitor', f'echo x > "{marker.as_posix()}"')
    (repo / 'NOTES.md').write_text('x\n', encoding='utf-8')
    _git(repo, '-c', 'core.fsmonitor=false', 'add', '.')
    _git(repo, '-c', 'core.fsmonitor=false', 'commit', '-qm', 'notes')
    assert study.status(vault, repo)['changed_docs'] == ['NOTES.md']
    assert not marker.exists()
