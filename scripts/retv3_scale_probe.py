"""RETV3-00 scale probe (usage: python scripts/retv3_scale_probe.py 0 100 300; POOL=n overrides the pool): does the prompt path still find the answer once memory grows past the pool?

Read-only on the real vault: copies memory/registry/state into a temp vault and adds
real pending review-candidate texts as extra active memories (distractors).
"""
import json, shutil, sys, tempfile, time
from pathlib import Path

REAL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REAL))
from brain_eleven.runtime.recall_probe import load_questions, covers, in_context, pending_candidate_texts
from brain_eleven.runtime import context as ctx
from brain_eleven.projects.registry import ProjectRegistry

pid = ProjectRegistry(REAL).resolve(REAL)['project_id']
doc = json.loads((REAL / '.claude' / 'validated-memory.json').read_text(encoding='utf-8'))
active = [m for m in doc['validated_memory'] if str(m.get('status') or 'active') == 'active']
pending = [t for _, t in pending_candidate_texts(REAL, pid)]
seen, distractors = set(), []
for t in pending:
    k = ' '.join(t.split()).lower()
    if k not in seen and 40 <= len(t) <= 600:
        seen.add(k); distractors.append(t)
questions = load_questions() + load_questions(REAL / '.brain-eleven/runtime/questions-w39.json')
config = REAL / '.claude' / 'ig-provider-config.json'
ctx.PROMPT_POOL = int(__import__('os').environ.get('POOL', ctx.PROMPT_POOL))
print('active', len(active), 'distractor pool', len(distractors), 'questions', len(questions))

def run(extra):
    tmp = Path(tempfile.mkdtemp(prefix='retv3-'))
    (tmp / '.claude').mkdir()
    for name in ('project-registry.json', 'project-state.json'):
        shutil.copy(REAL / '.claude' / name, tmp / '.claude' / name)
    added = [{'memory_id': f'mem_dist{i:05d}', 'status': 'active', 'type': 'decision', 'content': t,
              'project_id': pid, 'timestamp': '2026-09-30T12:00:00+00:00', 'confidence': 0.8}
             for i, t in enumerate(distractors[:extra])]
    data = dict(doc); data['validated_memory'] = doc['validated_memory'] + added
    (tmp / '.claude' / 'validated-memory.json').write_text(json.dumps(data), encoding='utf-8')
    comp = ctx._legacy_context_compiler()(str(tmp), project_id=pid)
    comp.memories = comp.memory_store.load()['validated_memory']
    pool = [m.get('memory_id') for m in comp._rank_memories(limit=ctx.PROMPT_POOL)]
    ctx.warm_prompt_providers(config, texts=[m['content'] for m in active + added])
    in_pool = found = 0
    slow = 0.0
    for q in questions:
        holders = {m['memory_id'] for m in active if covers(m.get('content', ''), q['groups'])}
        in_pool += bool(holders & set(pool))
        started = time.perf_counter()
        out = ctx._compile_project_scoped_v1(tmp, pid, prompt=q['question'], provider_config_path=config)
        slow = max(slow, time.perf_counter() - started)
        found += in_context(out.get('context', ''), q['groups']) == 'WHOLE'
    shutil.rmtree(tmp, ignore_errors=True)
    return {'memories': len(active) + extra, 'answer_in_pool': in_pool, 'answer_delivered': found,
            'of': len(questions), 'max_seconds': round(slow, 2)}

for extra in [int(a) for a in sys.argv[1:]] or [0, 100, 300]:
    print(json.dumps(run(min(extra, len(distractors)))), flush=True)
