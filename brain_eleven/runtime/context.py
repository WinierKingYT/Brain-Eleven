"""One measured context chain for evaluation, hooks, and manual inspection."""
from dataclasses import replace
import re
from time import perf_counter
from brain_eleven.runtime.storage import RuntimeConfig, identity, now, write_json
from brain_eleven.runtime.worker import allowed
from scripts.task_state_context import TaskStateComposer
from context_router import ContextRouter, RoutingOptions
from authority import AuthorityResolver, AuthorityOptions
from retrieval_decision_v2 import RetrievalDecisionEngine, DecisionOptions, NeedPlan
from context_density_v2 import ContextDensityEngine, DensityOptions
from context_compiler_v2 import ContextCompilerV2
from context_compiler_v2.models import CompilationRequest, CompilationOptions, BudgetContract
from context_compiler_v2.safety import contains_secret
from context_compiler_v2.tokenizer import ConservativeTokenEstimator
from context_compiler_v2.adapters import CompilerEvidenceAdapter, CompilerSnapshot


# V2 may be computed for comparison in a separately reviewed path, but it is
# not a model-facing provider while the product remains in SHADOW.  Keep this
# allow-list local to the delivery boundary so a provider label cannot drift
# away from the text that is actually returned.
MODEL_FACING_V1_PROVIDERS = frozenset({'V1', 'W06B_TASK_AWARE'})


def _normalize_v1_state_identity(context, state):
    """Retain the legacy normal-turn state identity markers."""
    if state is None:
        return context
    record_ids = []
    for attribute in ('active_work_items', 'active_requirements', 'active_blockers', 'constraints', 'risks'):
        records = getattr(state, attribute, ())
        for record in records if isinstance(records, (list, tuple)) else ():
            record_id = record.get('id') if isinstance(record, dict) else None
            if isinstance(record_id, str) and record_id and record_id not in record_ids:
                record_ids.append(record_id)
    if not record_ids:
        return context
    return context + '\n\n## STATE RECORD IDS\n' + '\n'.join(f'- {item}' for item in record_ids)


def _legacy_context_compiler():
    """Load the legacy compiler without invoking its public Companion path."""
    from brain_eleven._legacy import load_legacy_module
    return load_legacy_module('brain_eleven_legacy_context_compiler', 'context-compiler.py').ContextCompiler


def _compile_project_scoped_v1(vault, project_id, *, budget=3000, human_approval=False):
    """Render the project-scoped legacy V1 projection for one task.

    The legacy public ``compile`` method reads Companion files and writes a
    bootstrap projection.  Native normal turns must use only its existing
    scoped primitives, so this adapter deliberately supplies empty related
    and unscoped note inputs to ``_generate_context_block``.
    """
    from scripts.capture_safety import evaluate_capture

    compiler = _legacy_context_compiler()(str(vault), project_id=project_id)
    document = compiler.memory_store.load()
    compiler.memories = document['validated_memory']
    compiler.source_memory_revision = document['revision']
    state = compiler._resolve_current_state()
    lineage = {
        'source_memory_revision': document['revision'],
        'source_state_revision': compiler.source_state_revision,
        'source_state_status': compiler.source_state_status,
    }

    def safe(text):
        return isinstance(text, str) and not contains_secret(text) and evaluate_capture(text).accepted

    memories = []
    for item in compiler._rank_memories(limit=5):
        content = item.get('content')
        if (not human_approval or item.get('is_approved', True) is True) and safe(content):
            memories.append(item)

    estimator = ConservativeTokenEstimator()
    context = _normalize_v1_state_identity(
        compiler._generate_context_block(memories, {}, '', '', state), state,
    )
    while memories and estimator.estimate(context).count > budget:
        memories.pop()
        context = _normalize_v1_state_identity(
            compiler._generate_context_block(memories, {}, '', '', state), state,
        )
    if not safe(context) or estimator.estimate(context).count > budget:
        context = ''
        status = 'DEGRADED'
    else:
        status = 'SUCCESS'

    # The same source snapshot guard used by SessionStart is required before
    # normal-turn V1 text becomes eligible for delivery.
    compiler._ensure_output_is_current(lineage)
    return {
        'status': status,
        'context': context,
        'selected_ids': [item['id'] for item in memories] if context else [],
        'project_id': project_id,
        'provider': 'V1',
        'delivery_approved': False,
        'delivered': False,
        'input_revisions': {
            'memory': document['revision'],
            'state': {
                project_id: {
                    'status': compiler.source_state_status,
                    'revision': compiler.source_state_revision,
                },
            },
        },
        'estimated_tokens': estimator.estimate(context).count,
    }


def compile_bootstrap(vault, project_root, *, budget=3000, session=''):
    """Bound the existing V1 compiler to canonical scoped bootstrap inputs."""
    from brain_eleven._legacy import load_legacy_module
    from scripts.capture_safety import evaluate_capture
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
    b1_enabled = runtime.load().get('b1_human_approval', False)
    memories = [item for item in compiler._rank_memories(limit=5)
                if (not b1_enabled or item.get('is_approved', True) is True)
                and safe(item['content'])]
    estimator = ConservativeTokenEstimator()
    # Unscoped Last Session, Open Loops and linked notes are not canonical
    # project inputs. Preserve V1 ranking and rendering without those surfaces.
    context = compiler._generate_context_block(memories, {}, '', '', state)
    while memories and estimator.estimate(context).count > budget:
        memories.pop()
        context = compiler._generate_context_block(memories, {}, '', '', state)
    reminder_context = None
    reminder_record = None
    try:
        from .maintenance_delivery import ack_reminder, latest_reminder
        reminder = latest_reminder(vault, project['project_id'], budget=600,
                                   delivery_key=session or None)
        reminder_text = reminder.get('context', '') if reminder.get('status') == 'FRESH' else ''
        if reminder_text:
            candidate_context = context + ('\n\n## Maintenance\n' if context else '## Maintenance\n') + reminder_text
            if estimator.estimate(candidate_context).count <= budget and safe(candidate_context):
                reminder_context = candidate_context
                reminder_record = reminder
    except Exception:
        # A stale or unavailable derived report must never block bootstrap.
        pass
    status = 'SUCCESS'
    effective_context = reminder_context or context
    if not safe(effective_context) or estimator.estimate(effective_context).count > budget:
        status, context = 'DEGRADED', ''
    compiler._ensure_output_is_current(lineage)
    current_project = allowed(vault, project_root)
    if runtime.load()['mode'] == 'OFF' or not current_project or current_project['project_id'] != project['project_id']:
        status, context = 'SCOPE_DISABLED', ''
    elif status == 'SUCCESS' and reminder_context and reminder_record:
        try:
            delivered = not session or ack_reminder(
                vault, project['project_id'], reminder_record['report_id'], session
            )
        except Exception:
            delivered = False
        context = reminder_context if delivered else context
    return {'status': status, 'context': context, 'selected_ids': [item['id'] for item in memories] if context else [],
            'project_id': project['project_id'], 'delivered': bool(context),
            'delivery_approved': bool(context), 'provider': 'V1',
            'estimated_tokens': estimator.estimate(context).count}


def compile_context(vault, project_root, request, *, client='manual', session='', turn='', budget=3000, event='UserPromptSubmit'):
    start = perf_counter()
    if event == 'SessionStart':
        result = compile_bootstrap(vault, project_root, budget=budget, session=session)
        result['elapsed_ms'] = round((perf_counter() - start) * 1000)
        return result
    runtime = RuntimeConfig(vault)
    config = runtime.load()
    if config['mode'] == 'OFF':
        return {'status': 'OFF', 'context': '', 'selected_ids': [], 'delivered': False,
                'delivery_approved': False, 'provider': 'OFF'}
    project = allowed(vault, project_root)
    if not project:
        return {'status': 'SCOPE_DISABLED', 'context': '', 'selected_ids': []}
    task = TaskStateComposer(vault, project_root).compose(request)
    if config.get('retrieval_mode') == 'W06B_TASK_AWARE' and event == 'UserPromptSubmit':
        result = compile_task_w06b(vault, task, budget=min(budget, 1024), human_approval=config.get('b1_human_approval', False))
        task_need = result.get('task_need', {})
        if task_need.get('status') in {'NO_NEED', 'AMBIGUOUS', 'UNAVAILABLE', 'INVALID'}:
            # The W06B fallback is also V1.  Keep the historical symbol
            # injectable for existing callers/tests without routing the
            # production fallback through the V2 compatibility function.
            fallback = compile_task_v1 if compile_task is _V2_COMPAT_COMPILE_TASK else compile_task
            legacy = fallback(vault, task, budget=budget,
                              human_approval=config.get('b1_human_approval', False))
            legacy['provider'] = 'V1'
            legacy['task_need_status'] = task_need.get('status')
            legacy['task_need_error_code'] = task_need.get('error_code')
            result = legacy
    else:
        result = compile_task_v1(vault, task, budget=budget,
                                 human_approval=config.get('b1_human_approval', False))
        result.setdefault('provider', 'V1')
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
    elif (config.get('retrieval_mode') != 'W06B_TASK_AWARE' and result.get('input_revisions')
          and not CompilerEvidenceAdapter(vault).inputs_current(CompilerSnapshot(result['input_revisions'], ()) )):
        result.update(status='STALE_INPUT', context='', selected_ids=[])
    # SHADOW computes no model-facing normal-turn context.  CANARY/ACTIVE
    # still use V1 only while the product-level V2 status remains SHADOW.
    if current_config['mode'] == 'SHADOW':
        result.update(context='', selected_ids=[])
    provider = result.get('provider')
    approved = (
        current_config['mode'] in {'CANARY', 'ACTIVE'}
        and provider in MODEL_FACING_V1_PROVIDERS
        and result.get('status') in {'SUCCESS', 'DEGRADED', 'EMPTY'}
        and bool(result.get('context'))
    )
    result['delivery_approved'] = approved
    result['delivered'] = approved
    telemetry = {key: value for key, value in result.items() if key != 'context'}
    telemetry.update(at=now(), client=client, session_hash=identity('session_', session), turn_hash=identity('turn_', turn),
                     elapsed_ms=round((perf_counter() - start) * 1000), project_id=project['project_id'])
    write_json(runtime.root / 'last-context.json', telemetry)
    result['elapsed_ms'] = telemetry['elapsed_ms']
    return result


def compile_task_w06b(vault, task, *, budget=1024, human_approval=False):
    """Native UserPromptSubmit W-06B path; SessionStart never calls this."""
    from brain_eleven._legacy import load_legacy_module
    from scripts.capture_safety import evaluate_capture
    compiler_type = load_legacy_module('brain_eleven_legacy_context_compiler', 'context-compiler.py').ContextCompiler
    project_id = getattr(getattr(task.task, 'project', None), 'project_id', None)
    if not project_id:
        return {'status': 'SCOPE_DISABLED', 'context': '', 'selected_ids': [], 'provider': 'V1'}
    compiler = compiler_type(str(vault), project_id=project_id)
    document = compiler.memory_store.load()
    compiler.memories = document['validated_memory']
    compiler.source_memory_revision = document['revision']
    compiler._resolve_current_state()
    source_state_revision = compiler.source_state_revision
    from .task_aware import select
    result = select(compiler, task.task, budget=budget, human_approval=human_approval)
    result['project_id'] = project_id
    # W-06B uses the legacy compiler projection; its state revision is an
    # opaque scalar, unlike the V2 adapter's per-project mapping.
    result['input_revisions'] = {'memory': document['revision'], 'state_revision': source_state_revision}
    current_document = compiler.memory_store.load()
    compiler._resolve_current_state()
    if (current_document.get('revision') != document['revision'] or
            compiler.source_state_revision != source_state_revision):
        return {'status': 'STALE_INPUT', 'context': '', 'selected_ids': [], 'provider': 'V1',
                'input_revisions': result['input_revisions']}
    if result.get('context') and (contains_secret(result['context']) or not evaluate_capture(result['context']).accepted):
        result.update(status='SAFETY_REJECTED', context='', selected_ids=[])
    return {key: value for key, value in result.items() if key != 'selected'}


def compile_task_v1(vault, task, *, budget=3000, human_approval=False):
    """Named normal-turn V1 adapter; never invokes a V2 compiler."""
    project_id = getattr(getattr(task.task, 'project', None), 'project_id', None)
    if not project_id:
        return {
            'status': 'SCOPE_DISABLED', 'context': '', 'selected_ids': [],
            'provider': 'V1', 'delivery_approved': False, 'delivered': False,
        }
    return _compile_project_scoped_v1(
        vault, project_id, budget=budget, human_approval=human_approval,
    )


def compile_task(vault, task, *, routing=None, budget=3000):
    """Historical V2 compatibility API for offline evaluation only.

    Native delivery never calls this function.  Keep the old name stable for
    existing evaluation callers while the normal hook path uses the explicit
    ``compile_task_v1`` adapter above.
    """
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


# Explicit name for new diagnostic callers; the compatibility name above is
# intentionally retained for the frozen evaluation provider.
compile_task_v2_shadow = compile_task
_V2_COMPAT_COMPILE_TASK = compile_task
