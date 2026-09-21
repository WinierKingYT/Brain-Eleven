"""IG-05 reachability check on the PUBLIC suite of phase15-corpus-v2 (dev only; holdout untouched).

Metric per IG01-A-EVALUATION-CONTRACT: context precision = |selected in required U useful, not forbidden| / |selected|,
macro mean over answerable cases, empty selection = 0; mandatory recall = required_selected / required (micro, as in IG-01-D).
Read-only: nothing in the repo changes. Signals are LABEL-FREE (scope, lifecycle, memory metadata, prompt text).
"""
import os, sys, re, statistics
from pathlib import Path
from tempfile import TemporaryDirectory
from collections import defaultdict
ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT)); os.chdir(ROOT)
from evals.schema import load_fixture, load_tasks
from evals.run import suite_task_paths
from evals.fixture_generator import build_vault
from brain_eleven.memory import MemoryStore

fixture = load_fixture(ROOT / 'evals/fixtures/phase15-contract.json')
tasks = load_tasks(suite_task_paths(ROOT / 'evals/corpus-v2', 'public'), fixture)

def cat(tid): return re.sub(r'_?\d+$', '', tid)

with TemporaryDirectory(prefix='ig05-') as tmp:
    vault = build_vault(fixture, Path(tmp) / 'vault', seed=0, noise_count=24)
    recs = MemoryStore(vault.root).load()['validated_memory']
    by_id = {r['memory_id']: r for r in recs}

    def in_scope(task):
        out = []
        for r in recs:
            if r.get('status') != 'active':
                continue
            if r.get('scope') == 'global' or (task.project_id and r.get('project_id') == task.project_id):
                out.append(r)
        return out

    rows = []
    for t in tasks:
        cands = in_scope(t)
        rows.append({'id': t.task_id, 'cat': cat(t.task_id), 'req': set(t.required), 'rel': set(t.required) | set(t.useful),
                     'forb': set(t.forbidden), 'cands': cands, 'prompt': t.prompt})

answerable = [r for r in rows if r['rel']]
print(f'public cases: {len(rows)} | with any relevant label (answerable): {len(answerable)} | with required: {sum(bool(r["req"]) for r in rows)}')
cover = sum(all(q in {c["memory_id"] for c in r['cands']} for q in r['req']) for r in rows if r['req'])
print(f'scope-complete candidate set contains ALL required memories in {cover}/{sum(bool(r["req"]) for r in rows)} cases '
      f'(current lexical router: 97/130 by the earlier count)')
print(f'avg in-scope active candidates per case: {statistics.mean(len(r["cands"]) for r in rows):.1f}')

def evaluate(select, label):
    pcases, sel_total, req_hit, req_tot, forb = [], 0, 0, 0, 0
    for r in rows:
        chosen = select(r)
        ids = [c['memory_id'] for c in chosen]
        sel_total += len(ids)
        forb += sum(i in r['forb'] for i in ids)
        if r['req']:
            req_hit += len(r['req'] & set(ids)); req_tot += len(r['req'])
        if r['rel']:
            good = [i for i in ids if i in r['rel'] and i not in r['forb']]
            pcases.append(len(good) / len(ids) if ids else 0.0)
    P = statistics.mean(pcases); R = req_hit / req_tot
    print(f'  {label:44s} macroP={P:.3f}  mandR={R:.3f}  avg_n={sel_total/len(rows):.2f}  forbidden={forb}')
    return P, R

print('\n-- label-free selectors over the scope-complete candidate set --')
evaluate(lambda r: r['cands'], 'select-all (control)')
conf = lambda c: c.get('confidence', 0)
for k in (1, 2, 3, 4):
    evaluate(lambda r, k=k: sorted(r['cands'], key=lambda c: -conf(c))[:k], f'top-{k} by memory confidence')
for th in (0.70, 0.75, 0.80):
    evaluate(lambda r, th=th: [c for c in r['cands'] if conf(c) >= th], f'confidence >= {th:.2f}  (in-sample threshold)')

# how often is a required memory the top-confidence candidate?
top1 = [r for r in rows if r['req'] and sorted(r['cands'], key=lambda c: -conf(c))[0]['memory_id'] in r['req']]
print(f'\nrequired memory is the TOP-confidence in-scope candidate in {len(top1)}/{sum(bool(r["req"]) for r in rows)} cases')
gap = []
for r in rows:
    if r['req']:
        req_conf = max((conf(c) for c in r['cands'] if c['memory_id'] in r['req']), default=None)
        other = [conf(c) for c in r['cands'] if c['memory_id'] not in r['req']]
        if req_conf is not None and other:
            gap.append(req_conf - max(other))
print(f'confidence margin of the required memory over the best non-required candidate: median {statistics.median(gap):+.3f}, min {min(gap):+.3f}, max {max(gap):+.3f}')

print('\n-- per category: top-1-by-confidence hits a relevant memory --')
cat_hit = defaultdict(lambda: [0, 0])
for r in rows:
    if r['rel']:
        best = sorted(r['cands'], key=lambda c: -conf(c))[0]['memory_id']
        cat_hit[r['cat']][1] += 1
        cat_hit[r['cat']][0] += best in r['rel'] and best not in r['forb']
for k, (h, n) in sorted(cat_hit.items()):
    print(f'  {k:38s} {h}/{n}')


# ================= harness fidelity + structural analysis ==========================
from evals.baseline import BaselineContextProvider
from evals.runtime_eval import budget_baseline
print('\n=== FIDELITY: reproduce the IG-01-D V1 baseline (recorded: precision 0.172308, mandatory recall 0.714286) ===')
with TemporaryDirectory(prefix='ig05b-') as tmp:
    vault = build_vault(fixture, Path(tmp) / 'vault', seed=17, noise_count=24)   # IG-01-D used seed 17 / noise 24
    prov = BaselineContextProvider()
    pcases, req_hit, req_tot, sel_tot = [], 0, 0, 0
    for t in tasks:
        res = prov.select(t, vault.root)
        ids = [i.id for i in res.selected_items]
        rel = set(t.required) | set(t.useful)
        sel_tot += len(ids)
        if t.required:
            req_hit += len(set(t.required) & set(ids)); req_tot += len(t.required)
        if rel:
            pcases.append(len([i for i in ids if i in rel and i not in set(t.forbidden)]) / len(ids) if ids else 0.0)
    print(f'  my metric on V1 (seed 17): macroP={statistics.mean(pcases):.6f}  mandR={req_hit/req_tot:.6f}  avg_n={sel_tot/len(tasks):.2f}')

print('\n=== STRUCTURE: does the label depend on the prompt, or on the project? ===')
proj_req = defaultdict(lambda: defaultdict(int)); proj_n = defaultdict(int)
for r, t in zip(rows, tasks):
    key = t.project_id or '(global)'
    proj_n[key] += 1
    proj_req[key][tuple(sorted(r['req']))] += 1
for k in sorted(proj_n):
    dist = sorted(proj_req[k].items(), key=lambda kv: -kv[1])
    top = dist[0]
    print(f'  {k:16s} cases={proj_n[k]:3d}  distinct required-sets={len(dist):2d}  most common covers {top[1]}/{proj_n[k]}  {top[0]}')

# information-free / leaky reference selectors
nonnoise = lambda r: [c for c in r['cands'] if not c['memory_id'].startswith('noise_')]
print('\n=== reference selectors (macro precision / mandatory recall) ===')
evaluate(nonnoise, 'perfect noise filter, select all real in scope')
# leaky project-prior: the required-set most common for the project (uses the LABELS -> not available at inference)
prior = {k: set(max(proj_req[k].items(), key=lambda kv: kv[1])[0]) for k in proj_req}
pt = {t.task_id: (t.project_id or '(global)') for t in tasks}
evaluate(lambda r: [c for c in r['cands'] if c['memory_id'] in prior[pt[r['id']]]], 'LEAKY project-prior (memorised labels)')


print('\n=== is the label a lookup on (project, template category)? ===')
grp = defaultdict(lambda: defaultdict(int)); grp_n = defaultdict(int)
for r, t in zip(rows, tasks):
    key = (t.project_id or '(global)', r['cat'])
    grp_n[key] += 1
    grp[key][tuple(sorted(r['rel']))] += 1
determ = sum(max(v.values()) for v in grp.values()) / len(rows)
print(f'  groups (project x category): {len(grp)}; cases whose full relevant-set equals their group\'s most common set: {determ:.1%}')
multi = [(k, len(v), grp_n[k]) for k, v in grp.items() if len(v) > 1]
print(f'  groups with more than one distinct relevant-set: {len(multi)} of {len(grp)}')
for k, nd, n in sorted(multi, key=lambda x: -x[2])[:5]:
    print(f'    {k}: {nd} distinct sets over {n} cases')
cat_prior = {k: set(max(v.items(), key=lambda kv: kv[1])[0]) for k, v in grp.items()}
key_of = {t.task_id: (t.project_id or '(global)', cat(t.task_id)) for t in tasks}
evaluate(lambda r: [c for c in r['cands'] if c['memory_id'] in cat_prior[key_of[r['id']]]], 'LEAKY (project x category) lookup')

print('\n=== do the memory TEXTS explain that lookup? sample of category -> relevant memory text (eleven_capture) ===')
with TemporaryDirectory(prefix='ig05c-') as tmp:
    v2 = build_vault(fixture, Path(tmp) / 'vault', seed=0, noise_count=24)
    txt = {m['memory_id']: m['content'] for m in MemoryStore(v2.root).load()['validated_memory']}
shown = set()
for r, t in zip(rows, tasks):
    if t.project_id == 'eleven_capture' and r['cat'] not in shown and len(shown) < 8:
        shown.add(r['cat'])
        print(f"  {r['cat']:22s} prompt words: {t.prompt[:62]!r}")
        for m in sorted(r['req']):
            print(f"      REQUIRED {m}: {txt.get(m, '?')[:78]}")


print('\n=== same prompt template, different labels? (eleven_capture, category p15_relevance) ===')
for r, t in zip(rows, tasks):
    if t.project_id == 'eleven_capture' and r['cat'] == 'p15_relevance':
        print(f"  {t.prompt}   required={sorted(r['req'])}  useful={sorted(set(t.useful))}")

# Bayes-style bound: a selector that cannot use the scenario NUMBER (digits stripped) -- the best it can do is a lookup on the template
norm = lambda s: re.sub(r'\d+', '#', s)
tmpl = defaultdict(lambda: defaultdict(int)); tmpl_n = defaultdict(int)
for r, t in zip(rows, tasks):
    tmpl[norm(t.prompt)][tuple(sorted(r['rel']))] += 1; tmpl_n[norm(t.prompt)] += 1
print(f'\n  distinct prompt templates (digits stripped): {len(tmpl)}; templates whose cases disagree on the relevant-set: {sum(len(v) > 1 for v in tmpl.values())}')
tprior = {k: set(max(v.items(), key=lambda kv: kv[1])[0]) for k, v in tmpl.items()}
print('\n=== BEST-CASE bound for ANY selector that treats the scenario number as arbitrary (leaky, in-sample) ===')
evaluate(lambda r: [c for c in r['cands'] if c['memory_id'] in tprior[norm(r['prompt'])]], 'lookup on digit-stripped prompt template')


print('\n=== FRONTIER: best macroP at each recall, for a selector that cannot use the scenario number (leaky upper bound) ===')
freq = {}
for k, v in tmpl.items():
    c = defaultdict(int)
    for rels, n in v.items():
        for m in rels:
            c[m] += n
    freq[k] = [m for m, _ in sorted(c.items(), key=lambda kv: -kv[1])]
for m in range(1, 9):
    def sel(r, m=m):
        top = set(freq[norm(r['prompt'])][:m])
        return [c for c in r['cands'] if c['memory_id'] in top]
    P, R = evaluate(sel, f'top-{m} most frequent relevant memories per template')
print('  (program floor: macroP >= 0.60 AND mandatory recall >= 0.80; IG-01-D provisional targets 0.65 / 0.85)')
