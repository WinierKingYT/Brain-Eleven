"""A session opened in a sub-folder (or in-tree git worktree) of a registered project belongs to it."""

import hashlib
import json

import pytest

from tests.test_pre13_runtime import _native_path, runtime  # noqa: F401
from brain_eleven.projects.registry import ProjectRegistry, normalize_registry_root
from brain_eleven.runtime import launcher
from brain_eleven.runtime.ownership import TranscriptOwnershipError, verify_transcript_ownership
from brain_eleven.runtime.storage import RuntimeConfig, read_json
from brain_eleven.runtime.worker import Worker


def _key(client, raw):
    return client + ':' + hashlib.sha256(raw.encode()).hexdigest()


def _claude(tmp_path, folder, session, cwd=None):
    document = {'type': 'user', 'sessionId': session,
                'message': {'role': 'user', 'content': 'We decided to use SQLite.'}}
    if cwd is not None:
        document['cwd'] = str(cwd)
    return _native_path(tmp_path, folder, 'claude', session, [document])


def _codex(tmp_path, cwd, session):
    return _native_path(tmp_path, cwd, 'codex', session, [
        {'type': 'session_meta', 'payload': {'session_id': session, 'cwd': str(cwd)}},
        {'type': 'response_item', 'payload': {'type': 'message', 'role': 'user', 'content': 'We decided to use SQLite.'}}])


# --- registry -----------------------------------------------------------------

def test_resolve_containing_walks_to_the_nearest_registered_root(tmp_path):
    vault = tmp_path / 'vault'
    outer = tmp_path / 'outer'
    inner = outer / 'packages' / 'inner'
    for folder in (vault, inner):
        folder.mkdir(parents=True)
    registry = ProjectRegistry(vault)
    outer_id = registry.register(outer)['project_id']
    inner_id = registry.register(inner)['project_id']

    assert registry.resolve_containing(outer)['project_id'] == outer_id
    assert registry.resolve_containing(outer / 'tests')['project_id'] == outer_id
    assert registry.resolve_containing(outer / '.claude' / 'worktrees' / 'foo' / 'src')['project_id'] == outer_id
    assert registry.resolve_containing(inner / 'src')['project_id'] == inner_id
    assert registry.resolve_containing(str(outer / 'packages'))['project_id'] == outer_id
    assert registry.resolve_containing(tmp_path / 'elsewhere') is None
    assert registry.resolve_containing(tmp_path / 'outer-sibling') is None
    for odd in (None, '', '   ', 'Q:\\nope\\missing', '\\\\server\\share\\x'):
        assert registry.resolve_containing(odd) is None
    # Exact-root semantics are unchanged.
    assert registry.resolve(outer / 'tests') is None


@pytest.mark.parametrize('change', ['archived', 'optout'])
def test_subfolder_of_disabled_project_is_rejected(runtime, tmp_path, monkeypatch, change):  # noqa: F811
    vault, project = runtime
    if change == 'archived':
        ProjectRegistry(vault).set_status(project, 'archived')
    else:
        ProjectRegistry(vault).set_proactive_capture(project, False)
    monkeypatch.setattr(launcher, 'ensure_service', lambda *a, **kw: True)
    assert launcher.hook(vault, 'claude', 'Stop', {'cwd': str(vault / 'tests'), 'session_id': 'x'}) == {}
    assert read_json(RuntimeConfig(vault).root / 'last-capture-claude.json')['outcome'] == 'CWD_NOT_REGISTERED'


# --- hook: capture ------------------------------------------------------------

@pytest.mark.parametrize('client', ['claude', 'codex'])
@pytest.mark.parametrize('sub', [('tests',), ('.claude', 'worktrees', 'foo')])
def test_subfolder_stop_is_queued_for_the_registered_project(runtime, tmp_path, monkeypatch, client, sub):  # noqa: F811
    vault, project = runtime
    cwd = vault.joinpath(*sub)
    cwd.mkdir(parents=True)
    path = _claude(tmp_path, cwd, 's1', cwd) if client == 'claude' else _codex(tmp_path, cwd, 's1')
    monkeypatch.setattr(launcher, 'ensure_service', lambda *a, **kw: True)
    assert launcher.hook(vault, client, 'Stop', {'cwd': str(cwd), 'session_id': 's1', 'transcript_path': str(path)}) == {}
    assert read_json(RuntimeConfig(vault).root / f'last-capture-{client}.json')['outcome'] == 'QUEUED'
    (job,) = (vault / '.brain-eleven' / 'capture' / 'queued').glob('*.json')
    event = json.loads(job.read_text(encoding='utf-8'))['event']
    assert event['project']['project_id'] == project
    assert event['project_root'] == normalize_registry_root(vault)
    assert Worker(vault).once()['status'] == 'PROCESSED'


def test_unregistered_cwd_is_still_rejected(runtime, tmp_path, monkeypatch):  # noqa: F811
    vault, _ = runtime
    monkeypatch.setattr(launcher, 'ensure_service', lambda *a, **kw: True)
    assert launcher.hook(vault, 'claude', 'Stop', {'cwd': str(tmp_path / 'vault-old' / 'tests'), 'session_id': 'x'}) == {}
    assert read_json(RuntimeConfig(vault).root / 'last-capture-claude.json')['outcome'] == 'CWD_NOT_REGISTERED'


# --- hook: context ------------------------------------------------------------

@pytest.mark.parametrize('event', ['SessionStart', 'UserPromptSubmit', 'SubagentStart'])
def test_subfolder_session_gets_context_for_the_registered_root(runtime, monkeypatch, event):  # noqa: F811
    vault, _ = runtime
    monkeypatch.setattr(launcher, 'ensure_service', lambda *a, **kw: True)
    calls = []

    def request(vault, route, payload, **kwargs):
        calls.append(payload)
        return {'status': 'SUCCESS', 'context': 'bağlam', 'delivered': True, 'delivery_approved': True, 'provider': 'V1'}
    monkeypatch.setattr(launcher, 'request_service', request)
    payload = {'cwd': str(vault / 'tests'), 'session_id': 'u', 'prompt': 'soru', 'agent_id': 'a'}
    result = launcher.hook(vault, 'claude', event, payload)
    output = result[0] if isinstance(result, tuple) else result
    assert 'bağlam' in output['hookSpecificOutput']['additionalContext']
    assert calls[0]['project_root'] == normalize_registry_root(vault)
    assert payload['cwd'] == str(vault / 'tests')


# --- ownership ----------------------------------------------------------------

def test_subfolder_claude_transcript_is_owned(runtime, tmp_path):  # noqa: F811
    vault, project = runtime
    sub = vault / '.claude' / 'worktrees' / 'foo'
    path = _claude(tmp_path, sub, 'own', sub)
    binding = verify_transcript_ownership(vault, path, 'claude', _key('claude', 'own'), project, vault)
    assert binding.project_id == project


def test_subfolder_claude_transcript_without_cwd_is_unverified(runtime, tmp_path):  # noqa: F811
    vault, project = runtime
    path = _claude(tmp_path, vault / 'tests', 'nocwd')
    with pytest.raises(TranscriptOwnershipError) as error:
        verify_transcript_ownership(vault, path, 'claude', _key('claude', 'nocwd'), project, vault)
    assert error.value.code == 'TRANSCRIPT_OWNERSHIP_UNVERIFIED'


def test_unregistered_folder_claude_transcript_is_not_owned(runtime, tmp_path):  # noqa: F811
    vault, project = runtime
    stranger = tmp_path / 'stranger'
    # Directory and recorded cwd both say "stranger"; the event claims the vault.
    path = _claude(tmp_path, stranger, 'stray', stranger)
    with pytest.raises(TranscriptOwnershipError):
        verify_transcript_ownership(vault, path, 'claude', _key('claude', 'stray'), project, vault)
    # A cwd that claims the vault cannot move a transcript out of another folder's directory.
    forged = _claude(tmp_path, stranger, 'forged', vault / 'tests')
    with pytest.raises(TranscriptOwnershipError):
        verify_transcript_ownership(vault, forged, 'claude', _key('claude', 'forged'), project, vault)


@pytest.mark.parametrize('client', ['claude', 'codex'])
def test_nested_project_transcript_is_not_owned_by_the_outer_project(runtime, tmp_path, client):  # noqa: F811
    vault, project = runtime
    nested = vault / 'nested'
    nested.mkdir()
    nested_id = ProjectRegistry(vault).register(nested, proactive_capture=True)['project_id']
    sub = nested / 'src'
    path = _claude(tmp_path, sub, 'n1', sub) if client == 'claude' else _codex(tmp_path, sub, 'n1')
    with pytest.raises(TranscriptOwnershipError) as error:
        verify_transcript_ownership(vault, path, client, _key(client, 'n1'), project, vault)
    assert error.value.code == 'TRANSCRIPT_OWNERSHIP_MISMATCH'
    assert verify_transcript_ownership(vault, path, client, _key(client, 'n1'), nested_id, nested).project_id == nested_id


def test_subfolder_codex_transcript_is_owned_and_foreign_cwd_is_not(runtime, tmp_path):  # noqa: F811
    vault, project = runtime
    owned = _codex(tmp_path, vault / 'tests', 'c1')
    assert verify_transcript_ownership(vault, owned, 'codex', _key('codex', 'c1'), project, vault).project_id == project
    foreign = _codex(tmp_path, tmp_path / 'vault-old', 'c2')
    with pytest.raises(TranscriptOwnershipError) as error:
        verify_transcript_ownership(vault, foreign, 'codex', _key('codex', 'c2'), project, vault)
    assert error.value.code == 'TRANSCRIPT_OWNERSHIP_MISMATCH'
