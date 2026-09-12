import json
from dataclasses import replace
from types import SimpleNamespace as N
import pytest

from brain_eleven.runtime.storage import RuntimeConfig, write_json, identity
from brain_eleven.runtime.migration import migrate
from brain_eleven.runtime.worker import Worker, enqueue, apply_candidate
from brain_eleven.runtime.context import compile_context
from brain_eleven.projects.registry import ProjectRegistry
from brain_eleven.state import StateService, StateStore
from brain_eleven.memory import MemoryStore
from context_density_v2 import ContextDensityEngine, DensityOptions


@pytest.fixture
def runtime(tmp_path):
    vault = tmp_path / 'vault'
    vault.mkdir()
    project = ProjectRegistry(vault).register(vault, proactive_capture=True)
    StateService(vault).init_project(project['project_id'], source={'type': 'user', 'reference': 'test'})
    migrate(vault)
    cfg = RuntimeConfig(vault)
    write_json(cfg.path, {'schema_version': 1, 'mode': 'CANARY', 'project_ids': [project['project_id']], 'local_model': None,
                          'transcript_roots': {'claude': [str(tmp_path)], 'codex': [str(tmp_path)]}})
    return vault, project['project_id']


def test_critical_missing_is_degraded():
    item = N(candidate_id='a', source_type='memory', project_id='p', content_type='lesson', lifecycle='ACTIVE', canonical_ref={'memory_id':'a'}, needs=('lesson',), decision_score=.8)
    source = N(status='SUCCESS', input_revisions={}, selected=(item,), need_plan=N(needs=(N(need_id='blocker', priority='critical'),)))
    result = ContextDensityEngine().select(source)
    assert result.status == 'DEGRADED'
    assert result.telemetry['missing_critical_needs'] == ['blocker']
    assert ContextDensityEngine().select(replace_namespace(source, selected=())).status == 'DEGRADED'


def replace_namespace(value, **changes):
    return N(**{**vars(value), **changes})


def test_diversity_weight_changes_actual_selection():
    def item(key, score):
        return N(candidate_id=key, source_type='memory', project_id='p', content_type='lesson', lifecycle='ACTIVE', canonical_ref={'memory_id':key}, needs=('lesson',), decision_score=score)
    source = N(status='SUCCESS', input_revisions={}, selected=(item('a', .9), item('b', .8), item('c', .7)), need_plan=N(needs=()))
    texts = {'a':'database sqlite local', 'b':'database sqlite local', 'c':'cache redis eviction'}
    full = ContextDensityEngine().select(source, options=DensityOptions(max_selected=2, diversity_lambda=1), candidate_texts=texts)
    varied = ContextDensityEngine().select(source, options=DensityOptions(max_selected=2, diversity_lambda=.1), candidate_texts=texts)
    assert [x.candidate_id for x in full.selected] == ['a', 'b']
    assert [x.candidate_id for x in varied.selected] == ['a', 'c']


def candidate(project, **changes):
    return {'candidate_id':'cand_test', 'candidate_type':'NEW_MEMORY','project_id':project,'scope':'project','content':'We decided to use SQLite for persistent storage.', 'memory_type':'decision','commitment':'COMMITTED','confidence':.97,'evidence_refs':['evd_test'], **changes}


def test_memory_receipt_is_atomic_and_replay_safe(runtime):
    vault, project = runtime
    item = candidate(project)
    op = identity('op_', 'test')
    first = apply_candidate(vault, item, op_id=op)
    assert first['status'] == 'SUCCESS'
    before = MemoryStore(vault).load()
    second = apply_candidate(vault, item, op_id=op)
    assert second['status'] == 'SUCCESS'
    assert MemoryStore(vault).load() == before
    assert op in before['operation_receipts']


def test_state_receipt_replay_does_not_duplicate_blocker(runtime):
    vault, project = runtime
    item = candidate(project, candidate_type='STATE_MUTATION', text='Build is currently failing', operation='ADD_BLOCKER', commitment='OBSERVED')
    op = identity('op_', 'state')
    assert apply_candidate(vault, item, op_id=op)['status'] == 'SUCCESS'
    before = StateStore(vault).load()
    assert apply_candidate(vault, item, op_id=op)['status'] == 'SUCCESS'
    assert StateStore(vault).load() == before


@pytest.mark.parametrize('client', ['claude', 'codex'])
def test_native_capture_to_other_client_context(runtime, client, tmp_path):
    vault, project = runtime
    text = 'We decided to use SQLite for persistent storage.'
    message = {'role':'user', 'content':[{'type':'input_text' if client == 'codex' else 'text','text':text}]}
    doc = {'type':'response_item','payload':{'type':'message', **message}} if client == 'codex' else {'type':'user','message':message}
    path = tmp_path / 'transcript.jsonl'
    path.write_text(json.dumps(doc) + '\n', encoding='utf-8')
    payload = {'session_id':'test-session','cwd':str(vault),'transcript_path':str(path)}
    enqueue(vault, client, payload)
    result = Worker(vault).once()
    assert result['status'] == 'PROCESSED', result
    assert len(MemoryStore(vault).load()['validated_memory']) == 1
    # Appending an assistant message cannot make another user decision.
    assistant = {'role':'assistant','content':[{'type':'output_text' if client == 'codex' else 'text','text':'We decided to use PostgreSQL instead.'}]}
    doc = {'type':'response_item','payload':{'type':'message', **assistant}} if client == 'codex' else {'type':'assistant','message':assistant}
    with path.open('a', encoding='utf-8') as stream:
        stream.write(json.dumps(doc) + '\n')
    enqueue(vault, client, payload)
    assert Worker(vault).once()['status'] == 'PROCESSED'
    assert len(MemoryStore(vault).load()['validated_memory']) == 1
    context = compile_context(vault, vault, 'Which database did we decide to use for persistent storage?', client='codex' if client == 'claude' else 'claude')
    assert context['status'] in {'SUCCESS','DEGRADED'}, context
    assert 'SQLite' in context['context'], context


def test_supersession_writes_successor_and_target_atomically(runtime):
    vault, project = runtime
    apply_candidate(vault, candidate(project), op_id=identity('op_', 'first'))
    old = MemoryStore(vault).load()['validated_memory'][0]['memory_id']
    new = candidate(project, candidate_id='cand_second', content='We decided to use PostgreSQL for persistent storage.')
    result = apply_candidate(vault, new, op_id=identity('op_', 'second'), approved=True, target_id=old)
    assert result['status'] == 'SUCCESS'
    records = MemoryStore(vault).load()['validated_memory']
    assert len(records) == 2
    assert records[0]['status'] == 'superseded'
    assert records[0]['superseded_by'] == records[1]['memory_id']


def test_review_replay_ignores_old_cas_but_rejects_changed_identity(runtime):
    vault, project = runtime
    item = candidate(project)
    op = identity('op_', 'accept')
    revision = MemoryStore(vault).revision()
    assert apply_candidate(vault, item, op_id=op, expected_revision=revision)['status'] == 'SUCCESS'
    before = MemoryStore(vault).load()
    assert apply_candidate(vault, item, op_id=op, expected_revision=revision)['status'] == 'SUCCESS'
    assert apply_candidate(vault, {**item, 'content': 'We decided to use PostgreSQL.'}, op_id=op)['status'] != 'SUCCESS'
    assert MemoryStore(vault).load() == before


def test_state_replay_reports_original_revision_and_id(runtime):
    vault, project = runtime
    item = candidate(project, candidate_type='STATE_MUTATION', text='Build is failing', operation='ADD_BLOCKER', commitment='OBSERVED')
    op = identity('op_', 'replay-state')
    revision = StateStore(vault).project_revision(project)
    first = apply_candidate(vault, item, op_id=op, expected_revision=revision)
    second = apply_candidate(vault, item, op_id=op, expected_revision=revision)
    assert first['record_id'] == second['record_id']
    assert second['revision_after'] == first['revision_after']
    assert second['replayed'] and not second['canonical_write']


def test_backup_restore_preserves_runtime_receipts(runtime, tmp_path):
    from memory_backup import create_backup, restore_backup, verify_backup
    vault, project = runtime
    apply_candidate(vault, candidate(project), op_id=identity('op_', 'backup-memory'))
    apply_candidate(vault, candidate(project, candidate_type='STATE_MUTATION', text='Build is failing', operation='ADD_BLOCKER', commitment='OBSERVED'), op_id=identity('op_', 'backup-state'))
    archive = tmp_path / 'runtime-backup.zip'
    create_backup(vault, archive)
    verify_backup(archive)
    restored = tmp_path / 'restored'
    restore_backup(archive, restored)
    assert MemoryStore(restored).load() == MemoryStore(vault).load()
    assert StateStore(restored).load() == StateStore(vault).load()


def test_store_replacement_cannot_discard_receipts(runtime):
    vault, project = runtime
    from brain_eleven.memory import MemoryStoreCorrupt
    store = MemoryStore(vault)
    apply_candidate(vault, candidate(project), op_id=identity('op_', 'replace'))
    with pytest.raises(MemoryStoreCorrupt):
        store.replace(store.empty_document())


def test_migration_repeats_and_safe_rollback(tmp_path):
    from brain_eleven.runtime.migration import rollback
    from brain_eleven.runtime.storage import read_json
    vault = tmp_path / 'empty'
    migrate(vault)
    cfg = RuntimeConfig(vault)
    backup = read_json(cfg.root / 'migration' / 'memory.json')
    migrate(vault)
    assert read_json(cfg.root / 'migration' / 'memory.json') == backup
    assert rollback(vault)['status'] == 'ROLLED_BACK'
    assert not MemoryStore(vault).path.exists()


def test_rollback_refuses_canonical_effects(runtime):
    from brain_eleven.runtime.migration import rollback
    vault, project = runtime
    apply_candidate(vault, candidate(project), op_id=identity('op_', 'rollback'))
    RuntimeConfig(vault).set_mode('OFF')
    with pytest.raises(ValueError, match='Canonical operations'):
        rollback(vault)


@pytest.mark.parametrize('action', ['accept', 'reject', 'expire'])
def test_review_terminal_state_erases_candidate_text(runtime, action):
    from brain_eleven.runtime.review import ReviewStore
    from brain_eleven.runtime.service import review_action
    from brain_eleven.runtime.storage import read_json
    vault, project = runtime
    store = ReviewStore(vault)
    key = store.add(candidate(project), 'REVIEW_REQUIRED', {'client':'codex'})
    if action == 'expire':
        value = read_json(store.path(key))
        value['expires_at'] = '2000-01-01T00:00:00+00:00'
        write_json(store.path(key), value)
        store.expire()
    else:
        review_action(vault, key, action, {'expected_revision':MemoryStore(vault).revision()})
    value = read_json(store.path(key))
    assert value['status'] in {'ACCEPTED', 'REJECTED', 'EXPIRED'}
    assert 'SQLite' not in json.dumps(value)
    assert 'candidate' not in value and 'accept_intent' not in value


def test_review_recovery_after_canonical_write_before_finish(runtime, monkeypatch):
    from brain_eleven.runtime.review import ReviewStore
    from brain_eleven.runtime.service import review_action
    vault, project = runtime
    store = ReviewStore(vault)
    key = store.add(candidate(project), 'REVIEW_REQUIRED', {'client':'codex'})
    payload = {'expected_revision':MemoryStore(vault).revision()}
    finish = ReviewStore.finish
    monkeypatch.setattr(ReviewStore, 'finish', lambda *args, **kwargs: (_ for _ in ()).throw(OSError('simulated crash')))
    with pytest.raises(OSError):
        review_action(vault, key, 'accept', payload)
    before = MemoryStore(vault).load()
    monkeypatch.setattr(ReviewStore, 'finish', finish)
    assert review_action(vault, key, 'accept', payload)['status'] == 'ACCEPTED'
    assert MemoryStore(vault).load() == before


@pytest.mark.parametrize('client', ['claude', 'codex'])
def test_incremental_reader_waits_for_complete_line_and_rejects_rewrite(runtime, tmp_path, client):
    from brain_eleven.runtime.evidence import read_increment
    vault, project = runtime
    path = tmp_path / 'append.jsonl'
    doc = {'type':'response_item','payload':{'type':'message','role':'user','content':'A clear message'}} if client == 'codex' else {'type':'user','message':{'role':'user','content':'A clear message'}}
    raw = json.dumps(doc)
    path.write_text(raw, encoding='utf-8')
    batch, cursor = read_increment(vault, path, client, 'session', project, '2026-09-06T00:00:00Z')
    assert not batch.messages and cursor['offset'] == 0
    path.write_text(raw+'\n', encoding='utf-8')
    batch, cursor = read_increment(vault, path, client, 'session', project, '2026-09-06T00:00:00Z', cursor)
    assert len(batch.messages) == 1
    path.write_text(raw.replace('clear', 'other')+'\n', encoding='utf-8')
    with pytest.raises(ValueError, match='TRANSCRIPT_REWRITTEN'):
        read_increment(vault, path, client, 'session', project, '2026-09-06T00:00:00Z', cursor)


def test_worker_retries_after_effect_before_ack_without_duplicate(runtime, tmp_path, monkeypatch):
    vault, project = runtime
    path = tmp_path / 'crash.jsonl'
    path.write_text(json.dumps({'type':'user','message':{'role':'user','content':candidate(project)['content']}})+'\n', encoding='utf-8')
    enqueue(vault, 'claude', {'session_id':'crash', 'cwd':str(vault),'transcript_path':str(path)})
    worker = Worker(vault)
    commit = worker.queue.commit
    monkeypatch.setattr(worker.queue, 'commit', lambda *args: (_ for _ in ()).throw(OSError('simulated crash')))
    worker.once()
    before = MemoryStore(vault).load()
    monkeypatch.setattr(worker.queue, 'commit', commit)
    assert worker.once()['status'] == 'PROCESSED'
    assert MemoryStore(vault).load() == before
    assert len(before['validated_memory']) == 1


@pytest.mark.parametrize('scope', ['OFF', 'optout', 'archived', 'foreign'])
def test_disabled_scope_never_captures_or_injects(runtime, tmp_path, scope):
    vault, project = runtime
    root = vault
    if scope == 'OFF':
        RuntimeConfig(vault).set_mode('OFF')
    elif scope == 'optout':
        ProjectRegistry(vault).set_proactive_capture(project, False)
    elif scope == 'archived':
        ProjectRegistry(vault).set_status(project, 'archived')
    else:
        root = tmp_path / 'foreign'
        root.mkdir()
    before = MemoryStore(vault).load()
    assert enqueue(vault, 'codex', {'cwd':str(root)})['status'] in {'OFF','SCOPE_DISABLED'}
    assert compile_context(vault, root, 'Which database?')['context'] == ''
    assert MemoryStore(vault).load() == before


@pytest.mark.parametrize('url', ['https://api.openai.com/v1', 'http://localhost/v1', 'http://127.0.0.1.evil.test/v1', 'http://user@127.0.0.1/v1'])
def test_optional_model_rejects_nonlocal_endpoints(url):
    from brain_eleven.runtime.model import propose
    assert propose({'url':url,'model':'test'}, N(content='A proposal')) == ([], 'LOCAL_MODEL_ENDPOINT_REJECTED')


def test_optional_model_failure_does_not_block_rules(runtime, monkeypatch):
    from brain_eleven.runtime.model import propose
    import httpx
    monkeypatch.setattr(httpx.Client, 'stream', lambda *args, **kwargs: (_ for _ in ()).throw(httpx.ConnectError('offline')))
    assert propose({'url':'http://127.0.0.1:1/v1','model':'test'}, N(content='A proposal')) == ([], 'LOCAL_MODEL_UNAVAILABLE')


@pytest.fixture
def api(runtime):
    from fastapi.testclient import TestClient
    from brain_eleven.runtime.service import create_app
    vault, _ = runtime
    with TestClient(create_app(vault, token='test-session-token', background=False), base_url='http://127.0.0.1') as client:
        yield client


def test_review_api_auth_origin_and_body_limits(api):
    assert api.get('/review').status_code == 200
    assert api.get('/api/runtime/status').status_code == 401
    headers = {'Authorization':'Bearer test-session-token'}
    assert api.get('/api/runtime/status', headers=headers).status_code == 200
    assert api.get('/api/runtime/status', headers={**headers,'Origin':'https://evil.example'}).status_code == 403
    assert api.get('/health', headers={'Host':'evil.example'}).status_code == 403
    assert api.post('/api/context', headers=headers, content='x'*32001).status_code == 413
    assert api.post('/api/context', headers=headers, content='[]').status_code == 400
    assert "frame-ancestors 'none'" in api.get('/review').headers['content-security-policy']


def test_review_api_accept_and_state_target(api, runtime):
    from brain_eleven.runtime.review import ReviewStore
    vault, project = runtime
    blocked = candidate(project, candidate_type='STATE_MUTATION', text='Build currently fails', operation='ADD_BLOCKER', commitment='OBSERVED')
    first = apply_candidate(vault, blocked, op_id=identity('op_', 'target'))
    proposal = {**blocked,'candidate_id':'cand_resolve','operation':'RESOLVE_BLOCKER','text':'Build issue has been resolved'}
    key = ReviewStore(vault).add(proposal, 'REVIEW_REQUIRED', {'client':'claude'})
    headers = {'Authorization':'Bearer test-session-token'}
    item = api.get('/api/review/candidates', headers=headers).json()['candidates'][0]
    assert item['targets'][0]['id'] == first['record_id']
    response = api.post('/api/review/candidates/'+key+'/accept', headers=headers,
        json={'expected_revision':item['expected_revision'],'target_id':first['record_id']})
    assert response.json()['status'] == 'ACCEPTED'


def test_install_repeat_uninstall_preserves_unrelated_hooks_and_settings(runtime, tmp_path):
    from brain_eleven.runtime.install import install, uninstall, client_paths, doctor
    from brain_eleven.runtime.storage import read_json
    vault, _ = runtime
    home = tmp_path / 'home'
    custom = {'theme':'dark', 'hooks':{'Stop':[{'hooks':[{'type':'command','command':'my-own-script'}]}]}}
    for path in client_paths(home).values():
        write_json(path, custom)
    install(vault, home=home)
    install(vault, home=home)
    assert doctor(vault, home=home)['status'] == 'READY'
    for path in client_paths(home).values():
        assert len(read_json(path)['hooks']['Stop']) == 2
    uninstall(vault)
    for path in client_paths(home).values():
        assert read_json(path) == custom


def test_install_validates_all_client_files_before_any_write(runtime, tmp_path):
    from brain_eleven.runtime.install import install, client_paths
    vault, _ = runtime
    home = tmp_path / 'invalid-home'
    paths = client_paths(home)
    write_json(paths['claude'], {'theme':'dark'})
    write_json(paths['codex'], {'hooks':{'Stop':'invalid'}})
    before = paths['claude'].read_bytes()
    with pytest.raises(ValueError):
        install(vault, home=home)
    assert paths['claude'].read_bytes() == before


@pytest.mark.parametrize('recovery', ['retry', 'uninstall'])
def test_interrupted_hook_upgrade_retains_ownership(runtime, tmp_path, monkeypatch, recovery):
    from brain_eleven.runtime import install as module
    from brain_eleven.runtime.storage import read_json
    vault, _ = runtime
    home = tmp_path / 'interrupted-home'
    custom = {'hooks': {'Stop': [{'hooks': [{'type': 'command', 'command': 'unrelated'}]}]}}
    for path in module.client_paths(home).values():
        write_json(path, custom)
    module.install(vault, home=home)
    original_command = module.hook_command
    monkeypatch.setattr(module, 'hook_command', lambda *args: original_command(*args) + ' --new-version')
    original_write = module.write_json
    codex_path = module.client_paths(home)['codex']
    def fail_replace(path, value):
        if path == codex_path:
            raise OSError('simulated replace failure')
        return original_write(path, value)
    monkeypatch.setattr(module, 'write_json', fail_replace)
    with pytest.raises(OSError):
        module.install(vault, home=home)
    manifest = read_json(RuntimeConfig(vault).root / 'installation.json')
    assert len(manifest['clients']['codex']['owned_entries']) == 2
    monkeypatch.setattr(module, 'write_json', original_write)
    if recovery == 'retry':
        module.install(vault, home=home)
        assert module.doctor(vault, home=home)['status'] == 'READY'
    module.uninstall(vault)
    for path in module.client_paths(home).values():
        assert read_json(path) == custom


@pytest.mark.parametrize('change', ['OFF', 'SHADOW', 'optout', 'revision'])
def test_native_context_revalidates_after_baseline_comparison(runtime, monkeypatch, change):
    from evals.baseline import BaselineContextProvider
    vault, project = runtime
    apply_candidate(vault, candidate(project), op_id=identity('op_', 'initial'))
    original = BaselineContextProvider.select
    def changed(self, *args, **kwargs):
        result = original(self, *args, **kwargs)
        if change in {'OFF', 'SHADOW'}:
            RuntimeConfig(vault).set_mode(change)
        elif change == 'optout':
            ProjectRegistry(vault).set_proactive_capture(project, False)
        else:
            apply_candidate(vault, candidate(project, candidate_id='cand_later', content='We decided to enable encrypted backups.'), op_id=identity('op_', 'later'))
        return result
    monkeypatch.setattr(BaselineContextProvider, 'select', changed)
    result = compile_context(vault, vault, 'Which database did we decide to use for persistent storage?', client='codex')
    assert not result['delivered']
    if change != 'SHADOW':
        assert not result['context'] and not result['selected_ids']


def test_hook_delivery_and_warn_continue(runtime, monkeypatch):
    from brain_eleven.runtime import launcher
    vault, _ = runtime
    monkeypatch.setattr(launcher, 'ensure_service', lambda *args, **kwargs: True)
    monkeypatch.setattr(launcher, 'request_service', lambda *args, **kwargs: {'status':'DEGRADED','context':'Safe context','delivered':True,'missing_critical_needs':['blocker']})
    payload = {'cwd':str(vault),'session_id':'s','turn_id':'1','prompt':'Continue'}
    output, path, record = launcher.hook(vault, 'codex', 'UserPromptSubmit', payload)
    assert output['hookSpecificOutput']['additionalContext'] == 'Safe context'
    assert 'systemMessage' in output and 'decision' not in output
    write_json(path, record)
    assert launcher.hook(vault, 'codex', 'UserPromptSubmit', payload) == {}


def test_full_local_service_lifecycle_and_native_cli_hook(runtime, tmp_path):
    import os
    import subprocess
    import sys
    import time
    from pathlib import Path
    from brain_eleven.runtime.launcher import ensure_service, request_service
    vault, project = runtime
    assert ensure_service(vault, wait=True)
    try:
        first = request_service(vault, '/api/runtime/status')
        assert first['mode'] == 'CANARY'
        from brain_eleven.runtime.storage import read_json
        service_before = read_json(RuntimeConfig(vault).root / 'service.json')
        assert ensure_service(vault, wait=True)
        assert read_json(RuntimeConfig(vault).root / 'service.json') == service_before
        path = tmp_path / 'native.jsonl'
        path.write_text(json.dumps({'type':'user','message':{'role':'user','content':candidate(project)['content']}})+'\n', encoding='utf-8')
        launcher = Path(__file__).resolve().parents[1] / 'brain_eleven/runtime/launcher.py'
        payload = {'cwd':str(vault),'session_id':'native-s','transcript_path':str(path)}
        from brain_eleven.runtime.install import hook_python
        command = [hook_python(), str(launcher), '--vault', str(vault), '--client', 'claude', '--event', 'Stop']
        hidden = {'creationflags': subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0}
        output = subprocess.run(command, input=json.dumps(payload), text=True, encoding='utf-8', capture_output=True, timeout=5, **hidden)
        assert output.returncode == 0
        assert json.loads(output.stdout) == {}
        deadline = time.monotonic() + 8
        while not MemoryStore(vault).load()['validated_memory'] and time.monotonic() < deadline:
            time.sleep(.1)
        assert len(MemoryStore(vault).load()['validated_memory']) == 1
        command[-3:] = ['codex', '--event', 'UserPromptSubmit']
        payload.update(prompt='Which database did we decide to use for persistent storage?', turn_id='native-turn')
        output = subprocess.run(command, input=json.dumps(payload), text=True, encoding='utf-8', capture_output=True, timeout=5, **hidden)
        assert output.returncode == 0
        hook_output = json.loads(output.stdout)
        assert 'hookSpecificOutput' in hook_output, hook_output
        assert 'SQLite' in hook_output['hookSpecificOutput']['additionalContext']
        observations = list((RuntimeConfig(vault).root / 'deliveries').glob('*.json'))
        assert len(observations) == 1
        observation = read_json(observations[0])
        assert observation['selected_ids'] and observation['v1_ids']
        assert observation['implementation_fingerprint']
    finally:
        request_service(vault, '/api/runtime/stop', {}, timeout=2)
        deadline = time.monotonic() + 8
        while (RuntimeConfig(vault).root / 'service.json').exists() and time.monotonic() < deadline:
            time.sleep(.1)


def test_manual_pass_flag_cannot_enable_active(runtime):
    vault, _ = runtime
    cfg = RuntimeConfig(vault)
    write_json(cfg.root / 'graduation.json', {'status':'PASS'})
    with pytest.raises(ValueError, match='Independent live'):
        cfg.set_mode('ACTIVE')
    assert cfg.load()['mode'] == 'CANARY'


def test_empty_human_labels_do_not_count_as_real_graduation(runtime):
    from brain_eleven.runtime.graduation import evaluate
    vault, _ = runtime
    result = evaluate(vault, {'schema_version':1,'label_source':'human_independent','labeler':'test','tasks':[],'captures':[]}, {})
    assert result['status'] == 'PENDING_REAL_USE'
    assert result['real_turns'] == 0
    assert not result['gates']['capture_precision_98']


def test_missing_delivery_and_model_labels_cannot_graduate(runtime):
    from brain_eleven.runtime.graduation import evaluate
    vault, _ = runtime
    with pytest.raises(ValueError, match='human'):
        evaluate(vault, {'schema_version':1,'label_source':'model','labeler':'test'}, {})
    with pytest.raises(ValueError, match='emitted native'):
        evaluate(vault, {'schema_version':1,'label_source':'human_independent','labeler':'test',
                        'tasks':[{'delivery_id':identity('delivery_', 'missing'),'confirmed_real_turn':True}]}, {})


def test_review_drops_model_extras_and_checks_actual_state_text(runtime):
    from brain_eleven.runtime.review import ReviewStore
    vault, project = runtime
    store = ReviewStore(vault)
    key = store.add(candidate(project, raw_transcript='must not survive'), 'MODEL_PROPOSAL', {'client':'codex','raw_transcript':'must not survive'})
    assert 'must not survive' not in store.path(key).read_text(encoding='utf-8')
    assert store.add(candidate(project, candidate_type='STATE_MUTATION', text='password=SuperSecretCredential123'), 'REVIEW_REQUIRED', {}) is None


def test_model_proposals_are_bounded_and_strip_untrusted_extra_keys(monkeypatch):
    from brain_eleven.runtime.model import propose
    import httpx
    response = httpx.Response(200, request=httpx.Request('POST','http://127.0.0.1/v1/chat/completions'),
        json={'choices':[{'message':{'content':json.dumps({'candidates':[{'content':'Use transactions for writes.','memory_type':'decision','raw_transcript':'discard'}]})}}]})
    from contextlib import contextmanager
    @contextmanager
    def stream(*args, **kwargs):
        yield response
    monkeypatch.setattr(httpx.Client, 'stream', stream)
    values, error = propose({'url':'http://127.0.0.1/v1','model':'local'}, N(content='We decided to use transactions for writes.'))
    assert error is None
    assert values == [{'content':'Use transactions for writes.','memory_type':'decision'}]


def test_every_active_blocker_has_a_separate_critical_need(runtime):
    from task_state_context import TaskStateComposer
    from retrieval_decision_v2.engine import build_need_plan
    vault, project = runtime
    ids = []
    for index, text in enumerate(['Build fails with locked database', 'Deployment is blocked by missing certificates']):
        result = apply_candidate(vault, candidate(project, candidate_type='STATE_MUTATION', text=text, operation='ADD_BLOCKER', commitment='OBSERVED'), op_id=identity('op_', index))
        ids.append(result['record_id'])
    needs = build_need_plan(TaskStateComposer(vault, vault).compose('Debug the build'))
    assert set(ids) <= {need.domain for need in needs.needs if need.priority == 'critical'}
    result = compile_context(vault, vault, 'Debug the build')
    if result['status'] == 'SUCCESS':
        assert all(key in result['context'] for key in ids)


def test_live_gate_computation_uses_observed_ids_and_human_labels(runtime):
    from brain_eleven.runtime.graduation import evaluate
    from evals.runtime_eval import implementation_fingerprint
    vault, project = runtime
    cfg = RuntimeConfig(vault)
    fingerprint = implementation_fingerprint()
    labels = {'schema_version':1,'label_source':'human_independent','labeler':'unit-test-fixture',
              'tasks':[], 'captures':[], 'project_leaks':0,'lifecycle_leaks':0}
    for index in range(40):
        key = identity('delivery_', 'synthetic-unit-fixture', index)
        write_json(cfg.root / 'deliveries' / (key+'.json'), {'status':'EMITTED','implementation_fingerprint':fingerprint,
            'selected_ids':['required','irrelevant'], 'v1_ids':['required'], 'session_hash':str(index%5), 'client':'codex' if index%2 else 'claude',
            'project_id':project,'context_elapsed_ms':50,'hook_elapsed_ms':100})
        labels['tasks'].append({'delivery_id':key, 'confirmed_real_turn':True, 'required':['required'], 'useful':[], 'forbidden':['irrelevant']})
    op = identity('op_', 'synthetic-capture')
    write_json(cfg.root/'capture-observations'/(op+'.json'), {'operation_id':op})
    labels['captures'] = [{'operation_id':op,'correct':False}]
    result = evaluate(vault, labels, {})
    assert result['precision'] == .5 and result['required_recall'] == 1
    assert not result['gates']['no_forbidden'] and not result['gates']['capture_precision_98']
    assert result['status'] != 'PASS'
    labels['tasks'].append(labels['tasks'][0])
    with pytest.raises(ValueError, match='duplicate'):
        evaluate(vault, labels, {})


@pytest.mark.parametrize('client,document,error', [
    ('codex', {'type':'unknown'}, 'UNSUPPORTED_CODEX_TRANSCRIPT'),
    ('codex', {'type':'response_item','payload':{'type':'unknown'}}, 'UNSUPPORTED_CODEX_ITEM'),
    ('claude', {'type':'unknown'}, 'UNSUPPORTED_CLAUDE_TRANSCRIPT'),
    ('claude', {'type':'user','message':{'role':'unknown','content':'abc'}}, 'UNSUPPORTED_MESSAGE_ROLE'),
    ('claude', {'type':'user','message':{'role':'user','content':42}}, 'UNSUPPORTED_MESSAGE_CONTENT'),
])
def test_unknown_native_shapes_fail_visibly(runtime, tmp_path, client, document, error):
    from brain_eleven.runtime.evidence import read_increment
    vault, project = runtime
    path = tmp_path / 'unknown.jsonl'
    path.write_text(json.dumps(document)+'\n', encoding='utf-8')
    with pytest.raises(ValueError, match=error):
        read_increment(vault, path, client, 's', project, '2026-09-06T00:00:00Z')


def test_transcript_larger_than_one_chunk_is_consumed_incrementally(runtime, tmp_path):
    from brain_eleven.runtime.evidence import read_increment
    vault, project = runtime
    path = tmp_path / 'large.jsonl'
    metadata = json.dumps({'type':'event_msg','payload':{'data':'x'*3000}})+'\n'
    message = json.dumps({'type':'response_item','payload':{'type':'message','role':'user','content':'We decided to use SQLite.'}})+'\n'
    path.write_text(metadata*720+message, encoding='utf-8')
    batch, cursor = read_increment(vault, path, 'codex', 's', project, '2026-09-06T00:00:00Z')
    assert cursor['has_more'] and not batch.messages
    batch, cursor = read_increment(vault, path, 'codex', 's', project, '2026-09-06T00:00:00Z', cursor)
    assert len(batch.messages) == 1 and not cursor['has_more']


def test_shadow_keeps_decision_in_review_and_no_canonical_write(runtime, tmp_path):
    from brain_eleven.runtime.review import ReviewStore
    vault, project = runtime
    RuntimeConfig(vault).set_mode('SHADOW')
    path = tmp_path / 'shadow.jsonl'
    path.write_text(json.dumps({'type':'user','message':{'role':'user','content':candidate(project)['content']}})+'\n', encoding='utf-8')
    enqueue(vault, 'claude', {'cwd':str(vault),'session_id':'shadow','transcript_path':str(path)})
    assert Worker(vault).once()['status'] == 'PROCESSED'
    assert not MemoryStore(vault).load()['validated_memory']
    assert ReviewStore(vault).list()[0]['status'] == 'PENDING'
    assert not compile_context(vault,vault,'Which database?')['delivered']


def test_hook_main_malformed_input_warns_without_blocking(runtime, monkeypatch, capsys):
    from brain_eleven.runtime.launcher import main
    import io
    import sys
    vault, _ = runtime
    monkeypatch.setattr(sys, 'stdin', N(buffer=io.BytesIO(b'{bad input')))
    assert main(['--vault',str(vault),'--client','codex','--event','Stop']) == 0
    output = json.loads(capsys.readouterr().out)
    assert 'systemMessage' in output and 'bad input' not in str(output)


def test_background_service_worker_drains_queue(api, runtime):
    assert api.get('/review.js').status_code == 200
    assert api.get('/review.css').status_code == 200
    headers = {'Authorization':'Bearer test-session-token'}
    assert api.post('/api/context',headers=headers,json={'invalid':True}).status_code == 400
    assert api.post('/api/runtime/stop',headers=headers,json={}).json()['status'] == 'STOPPING'
    assert api.post('/api/review/candidates/invalid/accept',headers=headers,json={}).status_code == 409


def test_installed_codex_shell_command_preserves_windowless_json_io(runtime, tmp_path):
    import os
    import shutil
    import subprocess
    from brain_eleven.runtime.install import hook_command
    vault, _ = runtime
    foreign = tmp_path / 'not-opted-in'
    foreign.mkdir()
    payload = {'cwd': str(foreign), 'session_id': 'synthetic-shell-contract'}
    command = hook_command(vault, 'codex', 'Stop')
    if os.name == 'nt':
        shell = shutil.which('pwsh') or shutil.which('powershell')
        assert shell, 'A Windows native hook shell is required'
        args = [shell, '-NoProfile', '-NonInteractive', '-Command', command]
    else:
        args = ['/bin/sh', '-c', command]
    result = subprocess.run(args, input=json.dumps(payload), text=True, encoding='utf-8', capture_output=True,
                            timeout=8, creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {}, result.stdout
