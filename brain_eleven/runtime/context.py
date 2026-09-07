"""One measured context chain for evaluation, hooks, and manual inspection."""
from dataclasses import replace
import re
from time import perf_counter
from brain_eleven.runtime.storage import RuntimeConfig, identity, now, write_json
from brain_eleven.runtime.worker import allowed
from task_state_context import TaskStateComposer
from context_router import ContextRouter, RoutingOptions
from authority import AuthorityResolver, AuthorityOptions
from retrieval_decision_v2 import RetrievalDecisionEngine, DecisionOptions, NeedPlan
from context_density_v2 import ContextDensityEngine, DensityOptions
from context_compiler_v2 import ContextCompilerV2
from context_compiler_v2.models import CompilationRequest, CompilationOptions, BudgetContract
from context_compiler_v2.safety import contains_secret
from context_compiler_v2.tokenizer import ConservativeTokenEstimator
from context_compiler_v2.adapters import CompilerEvidenceAdapter, CompilerSnapshot


def compile_bootstrap(vault, project_root, *, budget=3000):
    """Bound the existing V1 compiler to canonical scoped bootstrap inputs."""
    from brain_eleven._legacy import load_legacy_module
    from capture_safety import evaluate_capture
    compiler_type = load_legacy_module('brain_eleven_legacy_context_compiler', 'context-compiler.py').ContextCompiler
    runtime = RuntimeConfig(vault)
    project = allowed(vault, project_root)
    if runtime.load()['mode'] == 'OFF' or not project:
        return {'status': 'OFF' if runtime.load()['mode'] == 'OFF' else 'SCOPE_DISABLED', 'context': '', 'selected_ids': [], 'delivered': False}
    compiler = compiler_type(str(vault), project_id=project['project_id'])
    document = compiler.memory_store.load()
    compiler.memories = document['validated_memory']
    compiler.source_memory_revision = document['revision']
    state = compiler._resolve_current_state()
    lineage = {'source_memory_revision': document['revision'], 'source_state_revision': compiler.source_state_revision,
               'source_state_status': compiler.source_state_status}
    def safe(text):
        return not contains_secret(text) and evaluate_capture(text).accepted
    memories = [item for item in compiler._rank_memories(limit=5) if safe(item['content'])]
    estimator = ConservativeTokenEstimator()
    # Unscoped Last Session, Open Loops and linked notes are not canonical
    # project inputs. Preserve V1 ranking and rendering without those surfaces.
    context = compiler._generate_context_block(memories, {}, '', '', state)
    while memories and estimator.estimate(context).count > budget:
        memories.pop()
        context = compiler._generate_context_block(memories, {}, '', '', state)
    status = 'SUCCESS'
    if not safe(context) or estimator.estimate(context).count > budget:
        status, context = 'DEGRADED', ''
    compiler._ensure_output_is_current(lineage)
    current_project = allowed(vault, project_root)
    if runtime.load()['mode'] == 'OFF' or not current_project or current_project['project_id'] != project['project_id']:
        status, context = 'SCOPE_DISABLED', ''
    return {'status': status, 'context': context, 'selected_ids': [item['id'] for item in memories] if context else [],
            'project_id': project['project_id'], 'delivered': bool(context), 'provider': 'V1',
            'estimated_tokens': estimator.estimate(context).count}


def compile_context(vault, project_root, request, *, client='manual', session='', turn='', budget=3000, event='UserPromptSubmit'):
    start = perf_counter()
    if event == 'SessionStart':
        result = compile_bootstrap(vault, project_root, budget=budget)
        result['elapsed_ms'] = round((perf_counter() - start) * 1000)
        return result
    runtime = RuntimeConfig(vault)
    config = runtime.load()
    if config['mode'] == 'OFF':
        return {'status': 'OFF', 'context': '', 'selected_ids': []}
    project = allowed(vault, project_root)
    if not project:
        return {'status': 'SCOPE_DISABLED', 'context': '', 'selected_ids': []}
    task = TaskStateComposer(vault, project_root).compose(request)
    result = compile_task(vault, task, routing=RoutingOptions(), budget=budget)
    result['project_id'] = project['project_id']
    if client in {'claude', 'codex'}:
        from types import SimpleNamespace
        from evals.baseline import BaselineContextProvider
        from evals.runtime_eval import budget_baseline, implementation_fingerprint
        reference, _ = budget_baseline(BaselineContextProvider().select(SimpleNamespace(task_id=task.task.task_id,
            project_id=project['project_id'], prompt=request), vault), request, budget)
        result['v1_ids'] = [x.id for x in reference.selected_items]
        result['implementation_fingerprint'] = implementation_fingerprint()
    # Baseline comparison also takes time: revalidate immediately before return.
    current_config = runtime.load()
    current_project = allowed(vault, project_root)
    if current_config['mode'] == 'OFF' or not current_project or current_project['project_id'] != project['project_id']:
        result.update(status='SCOPE_DISABLED', context='', selected_ids=[])
    elif result.get('input_revisions') and not CompilerEvidenceAdapter(vault).inputs_current(CompilerSnapshot(result['input_revisions'], ())):
        result.update(status='STALE_INPUT', context='', selected_ids=[])
    result['delivered'] = current_config['mode'] in {'CANARY', 'ACTIVE'} and bool(result.get('context'))
    telemetry = {key: value for key, value in result.items() if key != 'context'}
    telemetry.update(at=now(), client=client, session_hash=identity('session_', session), turn_hash=identity('turn_', turn),
                     elapsed_ms=round((perf_counter() - start) * 1000), project_id=project['project_id'])
    write_json(runtime.root / 'last-context.json', telemetry)
    result['elapsed_ms'] = telemetry['elapsed_ms']
    return result


def compile_task(vault, task, *, routing=None, budget=3000):
    """Exact read-only production chain, also used by offline evaluators."""
    routing = routing or RoutingOptions()
    router = ContextRouter(vault).route(task, routing)
    authority = AuthorityResolver(vault).resolve(task, router, AuthorityOptions(scope_mode=routing.scope_mode,
        selected_project_ids=routing.selected_project_ids, include_global=routing.include_global, history_mode=routing.history_mode))
    if authority.status not in {'SUCCESS', 'DEGRADED', 'EMPTY'}:
        return {'status': authority.status, 'context': '', 'selected_ids': [], 'warnings': ['CONTEXT_UNAVAILABLE']}
    adapter = CompilerEvidenceAdapter(vault)
    snapshot = adapter.snapshot(task, authority)
    estimator = ConservativeTokenEstimator()
    texts = {item.resolution.candidate_id: item.text for item in snapshot.candidates if not contains_secret(item.text)}
    decision = RetrievalDecisionEngine().select(task, router, authority, options=DecisionOptions(max_selected=len(router.candidates)), candidate_texts=texts)
    decision = replace(decision, input_revisions=dict(authority.input_revisions))
    # Rendered task text covers explicit constraints; only stored evidence
    # needs require a selected canonical candidate.
    decision = replace(decision, need_plan=NeedPlan(tuple(n for n in decision.need_plan.needs if n.kind != 'task')))
    selected = tuple(replace(item, estimated_tokens=estimator.estimate(texts[item.candidate_id]).count)
                     for item in decision.selected if item.candidate_id in texts)
    decision = replace(decision, selected=selected)
    density = ContextDensityEngine().select(decision, options=DensityOptions(max_selected=20), candidate_texts=texts)
    if density.status not in {'SUCCESS', 'DEGRADED', 'EMPTY'}:
        return {'status': 'INSUFFICIENT_BUDGET' if density.error == 'MANDATORY_CONTEXT_UNSATISFIED' else density.status,
                'context': '', 'selected_ids': [], 'warnings': [density.error or 'SELECTION_UNAVAILABLE']}
    bundle = ContextCompilerV2(vault).compile(CompilationRequest(task, authority, BudgetContract(budget), selection=density), CompilationOptions(cache_enabled=False))
    missing = density.telemetry.get('missing_critical_needs', [])
    status = bundle.status
    if missing and status in {'SUCCESS', 'EMPTY'}:
        status = 'DEGRADED'
    context = bundle.rendered_context
    if status not in {'SUCCESS', 'DEGRADED', 'EMPTY'} or not adapter.inputs_current(snapshot):
        context = ''
        if not adapter.inputs_current(snapshot):
            status = 'STALE_INPUT'
    return {'status': status, 'context': context, 'selected_ids': [item.candidate_id for item in bundle.selected] if context else [],
              'missing_critical_needs': missing, 'warnings': list(bundle.warnings), 'input_revisions': dict(snapshot.revisions),
              'estimated_tokens': estimator.estimate(context).count, 'density': dict(density.metrics)}
