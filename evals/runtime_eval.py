"""Independent labeled evaluation of production PRE-13 and budgeted V1 order.

Labels never enter either provider. This is synthetic regression evidence,
not live graduation. Reports contain IDs and measurements only.
"""
import argparse
from dataclasses import replace
import hashlib
import json
import math
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter
from .baseline import BaselineContextProvider
from .runtime_provider import RuntimeContextProvider
from .fixture_generator import build_vault
from .schema import load_fixture, load_tasks
from .run import suite_task_paths, check_corpus
from .metrics import evaluate_selection
from context_compiler_v2.models import BudgetContract
from context_compiler_v2.tokenizer import ConservativeTokenEstimator
from context_compiler_v2.safety import escape_untrusted_text, contains_secret
from brain_eleven.runtime.storage import write_json

ROOT = Path(__file__).resolve().parents[1]


def implementation_fingerprint():
    digest = hashlib.sha256()
    paths = []
    for name in ('brain_eleven', 'scripts', 'context_router', 'authority', 'retrieval_decision_v2', 'context_density_v2', 'context_compiler_v2', 'evals'):
        paths.extend((ROOT / name).rglob('*.py'))
    for path in sorted(paths):
        digest.update(path.relative_to(ROOT).as_posix().encode())
        digest.update(path.read_bytes().replace(b'\r\n', b'\n'))
    return digest.hexdigest()


def budget_baseline(result, prompt, budget):
    """Keep legacy V1 order; whole records compete under the same token ceiling.

    V1 has no task-aware ranking or budget of its own. The adapter supplies
    framing and conservative accounting; it cannot consult relevance labels.
    """
    estimator = ConservativeTokenEstimator()
    contract = BudgetContract(budget)
    rendered = '[BRAIN-ELEVEN TASK CONTEXT v1]\nTASK\n' + escape_untrusted_text(prompt) + '\n[END BRAIN-ELEVEN CONTEXT]'
    chosen = []
    for item in result.selected_items:
        if contains_secret(item.content):
            continue
        line = '\n- [' + item.id + '; ' + item.memory_type + '] ' + escape_untrusted_text(item.content)
        estimate = estimator.estimate(rendered + line)
        if estimate.count <= contract.usable_tokens and estimate.byte_count <= contract.hard_byte_limit:
            chosen.append(item)
            rendered += line
    return replace(result, selected_items=tuple(chosen)), estimator.estimate(rendered).count


def summarize(cases):
    selected = sum(c['selected_count'] for c in cases)
    required = sum(c['required_count'] for c in cases)
    return {'precision': sum(c['relevant_selected_count'] for c in cases) / selected if selected else 0,
            'required_recall': sum(c['required_selected_count'] for c in cases) / required if required else 1,
            'forbidden': sum(c['forbidden_context_count'] for c in cases),
            'project_leaks': sum(c['wrong_project_leakage_count'] for c in cases),
            'lifecycle_leaks': sum(c['superseded_leakage_count'] + c['resolved_leakage_count'] for c in cases)}


def run(suite='public', budget=2048, noise_count=24):
    fixture = load_fixture(ROOT / 'evals/fixtures/phase15-contract.json')
    corpus = ROOT / 'evals/corpus-v2'
    check_corpus(corpus, fixture)
    tasks = load_tasks(suite_task_paths(corpus, suite), fixture)
    provider = RuntimeContextProvider(budget)
    baseline = BaselineContextProvider()
    rows, latencies = [], []
    with TemporaryDirectory(prefix='brain-pre13-eval-') as tmp:
        vault = build_vault(fixture, Path(tmp) / 'vault', seed=0, noise_count=noise_count)
        for task in tasks:
            started = perf_counter()
            selected = provider.select(task, vault.root)
            latencies.append((perf_counter() - started) * 1000)
            reference, tokens = budget_baseline(baseline.select(task, vault.root), task.prompt, budget)
            rows.append({'task_id':task.task_id, 'runtime':evaluate_selection(task, fixture, selected).metrics.as_dict(),
                         'v1':evaluate_selection(task, fixture, reference).metrics.as_dict(),
                         'runtime_ids':[x.id for x in selected.selected_items], 'v1_ids':[x.id for x in reference.selected_items],
                         'runtime_tokens':provider.last_result['estimated_tokens'], 'v1_tokens':tokens,
                         'runtime_status':provider.last_result['status']})
    actual, prior = summarize([r['runtime'] for r in rows]), summarize([r['v1'] for r in rows])
    gates = {'precision_70':actual['precision'] >= .70, 'required_recall_80':actual['required_recall'] >= .80,
             'no_forbidden':actual['forbidden'] == 0, 'no_project_leaks':actual['project_leaks'] == 0, 'no_lifecycle_leaks':actual['lifecycle_leaks'] == 0,
             'nonregression_precision':actual['precision'] >= prior['precision'], 'nonregression_recall':actual['required_recall'] >= prior['required_recall']}
    return {'schema_version':1, 'evidence_type':'SYNTHETIC_LABELED', 'measurement':'independent_labels', 'suite':suite,
            'implementation_fingerprint':implementation_fingerprint(), 'budget':budget, 'v1_budget_protocol':'legacy_order_whole_records_conservative_ceiling',
            'noise_count':noise_count, 'case_count':len(rows), 'runtime':actual, 'v1':prior, 'gates':gates,
            'context_p95_ms':round(sorted(latencies)[max(0, math.ceil(len(latencies)*.95)-1)], 2),
            'status':'PASS' if all(gates.values()) else 'FAIL', 'cases':rows}


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--suite', choices=['smoke','public','holdout','all'], default='public')
    parser.add_argument('--report', required=True, type=Path)
    parser.add_argument('--noise-count', type=int, default=24)
    args = parser.parse_args(argv)
    result = run(args.suite, noise_count=args.noise_count)
    write_json(args.report, result)
    print(json.dumps({key:value for key,value in result.items() if key != 'cases'}, indent=2))
    return 0 if result['status'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
