"""One measured context chain for evaluation, hooks, and manual inspection."""
from dataclasses import replace
import math
import os
from pathlib import Path
import re
import threading
from time import perf_counter
from brain_eleven.runtime.storage import RuntimeConfig, identity, now, read_json, write_json
from brain_eleven.runtime.worker import allowed
from brain_eleven.memory.scope import infer_memory_scope
from .capture_safety import evaluate_capture
from .task_state_context import TaskStateComposer
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
MAX_V1_STATE_ID_MARKERS = 64


def _normalize_v1_state_identity(context, state):
    """Retain the legacy normal-turn state identity markers."""
    if state is None:
        return context
    record_ids = []
    for attribute in ('active_work_items', 'active_requirements', 'active_blockers', 'constraints', 'risks'):
        records = getattr(state, attribute, ())
        for record in records if isinstance(records, (list, tuple)) else ():
            if len(record_ids) >= MAX_V1_STATE_ID_MARKERS:
                break
            record_id = record.get('id') if isinstance(record, dict) else None
            if isinstance(record_id, str) and record_id and record_id not in record_ids:
                record_ids.append(record_id)
        if len(record_ids) >= MAX_V1_STATE_ID_MARKERS:
            break
    if not record_ids:
        return context
    return context + '\n\n## STATE RECORD IDS\n' + '\n'.join(f'- {item}' for item in record_ids)


def _legacy_context_compiler():
    """Load the legacy compiler without invoking its public Companion path."""
    from brain_eleven._legacy import load_legacy_module
    return load_legacy_module('brain_eleven_legacy_context_compiler', 'context-compiler.py').ContextCompiler


def _rank_prompt_candidates(query, baseline, ranked_pool, *, project_id, stable_key,
                           embedding_provider, reranker):
    """Semantically rerank the eligible pool within the V1 scope tiers.

    Candidate counts and scope tiers come from the current top-five V1 result;
    any eligible pool candidate from a represented tier may win a slot. No V1
    score floor applies: the memories a prompt asks about are usually ranked
    below the static top five (W39 probe, 2026-09-29), so a floor made prompt
    retrieval unable to change what is delivered.
    """
    if not isinstance(query, str) or not query.strip() or len(baseline) < 2:
        return list(baseline)

    def tier(item):
        return 0 if project_id and infer_memory_scope(item)[2] == project_id else 1

    counts = {}
    for item in baseline:
        item_tier = tier(item)
        counts[item_tier] = counts.get(item_tier, 0) + 1

    eligible = {item_tier: [] for item_tier in counts}
    for item in ranked_pool:
        item_tier = tier(item)
        if item_tier in eligible:
            eligible[item_tier].append(item)

    candidates = [item for item_tier in sorted(eligible) for item in eligible[item_tier]]
    if len(candidates) < len(baseline):
        return list(baseline)

    try:
        vectors = _embed_cached(embedding_provider, [query, *(str(item.get("content", "")) for item in candidates)])
        if vectors is None:
            return list(baseline)
        query_vector = vectors[0]

        def cosine(left, right):
            if len(left) != len(right) or not left:
                raise ValueError("embedding dimensions differ")
            numerator = sum(float(a) * float(b) for a, b in zip(left, right))
            left_norm = math.sqrt(sum(float(value) ** 2 for value in left))
            right_norm = math.sqrt(sum(float(value) ** 2 for value in right))
            if left_norm == 0 or right_norm == 0:
                return 0.0
            return numerator / (left_norm * right_norm)

        semantic = [cosine(query_vector, vector) for vector in vectors[1:]]
        # The cross-encoder is the expensive step (~30 ms per pair on CPU), so
        # only the best embedding matches of each tier reach it.
        shortlist = []
        for item_tier in sorted(counts):
            members = [index for index, item in enumerate(candidates) if tier(item) == item_tier]
            members.sort(key=lambda index: (-semantic[index], stable_key(candidates[index])))
            shortlist.extend(members[:max(RERANK_SHORTLIST, counts[item_tier])])
        candidates = [candidates[index] for index in shortlist]
        semantic_scores = [semantic[index] for index in shortlist]
        reranked = reranker.rerank(
            query, [str(item.get("content", "")) for item in candidates]
        )
        if reranked.status != "EMBEDDING_AVAILABLE" or len(reranked.scores) != len(candidates):
            return list(baseline)
        scores = [float(value) for value in reranked.scores]
        if any(not math.isfinite(value) for value in scores):
            return list(baseline)

        ranked = {}
        for item, semantic, cross_encoder in zip(candidates, semantic_scores, scores):
            ranked.setdefault(tier(item), []).append((item, cross_encoder, semantic))
        result = []
        for item_tier in sorted(counts):
            ordered = sorted(
                ranked.get(item_tier, []),
                key=lambda entry: (-entry[1], -entry[2], stable_key(entry[0])),
            )
            result.extend(item for item, _, _ in ordered[:counts[item_tier]])
        return result if len(result) == len(baseline) else list(baseline)
    except Exception:
        # Retrieval is optional; preserve the exact V1 ordering if a provider
        # is unavailable, malformed, or fails during a prompt.
        return list(baseline)



# Prompt-time providers live for the service process: constructing them loads
# the local models (3-17 s), which does not fit the 2 s hook budget per prompt.
RERANK_SHORTLIST = 20
_EMBEDDING_CACHE_LIMIT = 5000
_PROVIDER_LOCK = threading.Lock()
_PROVIDER_CACHE = {}
_EMBEDDING_CACHE = {}


def _embed_cached(provider, texts):
    """Return one vector per text, embedding only texts not seen before."""
    prefix = (getattr(provider, 'provider_id', ''), getattr(provider, 'model', ''))
    missing = list(dict.fromkeys(text for text in texts if (prefix, text) not in _EMBEDDING_CACHE))
    if missing:
        embedded = provider.embed(missing)
        if embedded.status != 'EMBEDDING_AVAILABLE' or len(embedded.vectors) != len(missing):
            return None
        if len(_EMBEDDING_CACHE) + len(missing) > _EMBEDDING_CACHE_LIMIT:
            _EMBEDDING_CACHE.clear()
        for text, vector in zip(missing, embedded.vectors):
            _EMBEDDING_CACHE[(prefix, text)] = tuple(vector)
    return [_EMBEDDING_CACHE[(prefix, text)] for text in texts]


def _prompt_providers(config_path):
    """Build the configured embedding provider and reranker once per config."""
    from brain_eleven.retrieval.embedding_provider import create_embedding_provider, create_reranker

    environment = dict(os.environ)
    # Prompt retrieval must fail closed when a model is not already
    # available; a normal user prompt must never trigger a download.
    environment['IG_LOCAL_MODELS_LOCAL_FILES_ONLY'] = 'true'
    path = Path(config_path)
    try:
        stamp = path.stat().st_mtime_ns
    except OSError:
        stamp = None
    key = (str(path.resolve()), stamp, *(environment.get(name, '') for name in (
        'IG_EMBEDDING_PROVIDER', 'IG_RERANKER_PROVIDER', 'IG_LOCAL_EMBEDDING_MODEL', 'IG_LOCAL_RERANKER_MODEL')))
    with _PROVIDER_LOCK:
        if key not in _PROVIDER_CACHE:
            _PROVIDER_CACHE.clear()
            _PROVIDER_CACHE[key] = (
                create_embedding_provider(config_path=path, environ=environment),
                create_reranker(config_path=path, environ=environment),
            )
        return _PROVIDER_CACHE[key]


def warm_prompt_providers(config_path=Path('.claude/ig-provider-config.json')):
    """Load prompt providers ahead of the first prompt; never raises."""
    try:
        embedding_provider, reranker = _prompt_providers(config_path)
        if _embed_cached(embedding_provider, ['warm-up']) is not None:
            reranker.rerank('warm-up', ['warm-up'])
    except Exception:
        pass


def _compile_project_scoped_v1(vault, project_id, *, budget=3000, human_approval=False,
                                prompt=None, provider_config_path=None):
    """Render the project-scoped legacy V1 projection for one task.

    The legacy public ``compile`` method reads Companion files and writes a
    bootstrap projection.  Native normal turns must use only its existing
    scoped primitives, so this adapter deliberately supplies empty related
    and unscoped note inputs to ``_generate_context_block``.
    """
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

    def eligible(item):
        content = item.get('content')
        return ((not human_approval or item.get('is_approved', True) is True)
                and safe(content))

    ranked = compiler._rank_memories(limit=5)
    memories = [item for item in ranked if eligible(item)]
    if isinstance(prompt, str) and prompt.strip() and memories:
        ranked_pool = compiler._rank_memories(limit=PROMPT_POOL)
        safe_pool = [item for item in ranked_pool if eligible(item)]
        try:
            embedding_provider, reranker = _prompt_providers(
                provider_config_path or Path('.claude/ig-provider-config.json'))
            memories = _rank_prompt_candidates(
                prompt,
                memories,
                safe_pool,
                project_id=project_id,
                stable_key=compiler._stable_memory_key,
                embedding_provider=embedding_provider,
                reranker=reranker,
            )
        except Exception:
            # Keep the normal prompt path available when optional retrieval
            # providers cannot be constructed.
            pass

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
        'selected_ids': [_memory_identity(item) for item in memories] if context else [],
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


BOOTSTRAP_POOL = 15
# Prompt-time candidate pool: wide enough to reach memories far below the
# static top five; bounded so a local cross-encoder stays prompt-fast.
PROMPT_POOL = 100
# SessionStart memory slots (owner decision C2, 2026-09-26): 5 left recall
# answers out with SLOT_LIMIT in a real session; the 3000-token budget still bounds it.
BOOTSTRAP_SLOTS = 8


def _memory_identity(item):
    """The canonical memory_id; the legacy numeric ``id`` is -1 for every new record."""
    return item.get('memory_id') or item.get('id')
NEAR_DUPLICATE = 0.6


def _stale_memory_ids(vault):
    """Memory ids flagged by the last staleness scan (step 6); empty if never scanned."""
    try:
        document = read_json(RuntimeConfig(vault).root / 'staleness.json', {}) or {}
    except (OSError, ValueError, TypeError):
        return set()
    return {x.get('memory_id') for x in document.get('stale_candidates', []) if isinstance(x, dict)}


def select_distinct(ranked, *, stale_ids=frozenset(), limit=5, reasons=None):
    """Roadmap step 9: spend the few bootstrap slots on distinct, current facts.

    Keeps V1's ranking order, but skips a memory that is a near-duplicate
    (word Jaccard >= NEAR_DUPLICATE) of one already chosen, and moves
    stale_candidate memories behind every non-stale one. Nothing is removed
    from memory; only this bounded selection changes.
    """
    from .review import _words
    ordered = [m for m in ranked if m.get('memory_id') not in stale_ids] + \
              [m for m in ranked if m.get('memory_id') in stale_ids]
    chosen, chosen_words = [], []
    for memory in ordered:
        mid = memory.get('memory_id')
        if len(chosen) == limit:
            if reasons is not None:
                reasons[mid] = 'SLOT_LIMIT'
            continue
        words = _words(memory.get('content', ''))
        twin = next((chosen[i].get('memory_id') for i, other in enumerate(chosen_words)
                     if words and other and len(words & other) / len(words | other) >= NEAR_DUPLICATE), None)
        if twin is not None:
            if reasons is not None:
                reasons[mid] = 'NEAR_DUPLICATE_OF:' + str(twin)
            continue
        chosen.append(memory)
        chosen_words.append(words)
    return chosen


def explain_bootstrap(vault, project_root, *, budget=3000):
    """Why each active memory of the project is, or is not, in the bootstrap context.

    Runs the same steps as compile_bootstrap (V1 ranking, approval and safety
    filters, distinct selection, token budget) but records where every memory
    stopped. Read-only; returns ids and reason codes, never memory text.
    """
    from brain_eleven._legacy import load_legacy_module
    compiler_type = load_legacy_module('brain_eleven_legacy_context_compiler', 'context-compiler.py').ContextCompiler
    runtime = RuntimeConfig(vault)
    project = allowed(vault, project_root)
    if runtime.load()['mode'] == 'OFF' or not project:
        return {'status': 'OFF' if runtime.load()['mode'] == 'OFF' else 'SCOPE_DISABLED', 'memories': {}}
    compiler = compiler_type(str(vault), project_id=project['project_id'])
    document = compiler.memory_store.load()
    compiler.memories = document['validated_memory']
    state = compiler._resolve_current_state()
    b1_enabled = runtime.load().get('b1_human_approval', False)
    stale = _stale_memory_ids(vault)
    ranked = compiler._rank_memories(limit=len(compiler.memories) + 1)
    reasons, pool = {}, []
    for position, item in enumerate(ranked):
        mid = item.get('memory_id')
        if b1_enabled and item.get('is_approved', True) is not True:
            reasons[mid] = 'NOT_APPROVED'
        elif contains_secret(item['content']) or not evaluate_capture(item['content']).accepted:
            reasons[mid] = 'SAFETY_FILTERED'
        elif position >= BOOTSTRAP_POOL:
            reasons[mid] = 'BELOW_POOL'
        else:
            pool.append(item)
    chosen = select_distinct(pool, stale_ids=stale, limit=BOOTSTRAP_SLOTS, reasons=reasons)
    estimator = ConservativeTokenEstimator()
    context = compiler._generate_context_block(chosen, {}, '', '', state)
    while chosen and estimator.estimate(context).count > budget:
        reasons[chosen.pop().get('memory_id')] = 'TOKEN_BUDGET'
        context = compiler._generate_context_block(chosen, {}, '', '', state)
    for item in chosen:
        reasons[item.get('memory_id')] = 'DELIVERED'
    memories = {mid: {'reason': reason, 'rank': next((i for i, m in enumerate(ranked) if m.get('memory_id') == mid), None),
                      'stale_candidate': mid in stale}
                for mid, reason in reasons.items()}
    counts = {}
    for entry in memories.values():
        key = entry['reason'].split(':')[0]
        counts[key] = counts.get(key, 0) + 1
    return {'status': 'SUCCESS', 'project_id': project['project_id'], 'active_ranked': len(ranked),
            'counts': counts, 'memories': memories}


def compile_bootstrap(vault, project_root, *, budget=3000, session=''):
    """Bound the existing V1 compiler to canonical scoped bootstrap inputs."""
    from brain_eleven._legacy import load_legacy_module
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
    pool = [item for item in compiler._rank_memories(limit=BOOTSTRAP_POOL)
            if (not b1_enabled or item.get('is_approved', True) is True)
            and safe(item['content'])]
    memories = select_distinct(pool, stale_ids=_stale_memory_ids(vault), limit=BOOTSTRAP_SLOTS)
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
    return {'status': status, 'context': context, 'selected_ids': [_memory_identity(item) for item in memories] if context else [],
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
            fallback_options = {
                'budget': budget,
                'human_approval': config.get('b1_human_approval', False),
            }
            if fallback is compile_task_v1:
                fallback_options.update(
                    prompt=request,
                    provider_config_path=(
                        os.environ.get('IG_PROVIDER_CONFIG')
                        or Path(project_root) / '.claude' / 'ig-provider-config.json'
                    ),
                )
            legacy = fallback(vault, task, **fallback_options)
            legacy['provider'] = 'V1'
            legacy['task_need_status'] = task_need.get('status')
            legacy['task_need_error_code'] = task_need.get('error_code')
            result = legacy
    else:
        result = compile_task_v1(vault, task, budget=budget,
                                 human_approval=config.get('b1_human_approval', False),
                                 prompt=request if event == 'UserPromptSubmit' else None,
                                 provider_config_path=(
                                     os.environ.get('IG_PROVIDER_CONFIG')
                                     or Path(project_root) / '.claude' / 'ig-provider-config.json'
                                 ))
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
    # SHADOW computes no model-facing normal-turn context, unless the owner
    # turned on shadow_recall (2026-09-27): then only V1 providers deliver.
    # CANARY/ACTIVE still use V1 only while the product-level V2 status
    # remains SHADOW.
    provider = result.get('provider')
    shadow_recall = (current_config['mode'] == 'SHADOW' and current_config.get('shadow_recall') is True
                     and provider in MODEL_FACING_V1_PROVIDERS)
    if current_config['mode'] == 'SHADOW' and not shadow_recall:
        result.update(context='', selected_ids=[])
    approved = (
        (current_config['mode'] in {'CANARY', 'ACTIVE'} or shadow_recall)
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


def compile_task_v1(vault, task, *, budget=3000, human_approval=False,
                    prompt=None, provider_config_path=None):
    """Named normal-turn V1 adapter; never invokes a V2 compiler."""
    project_id = getattr(getattr(task.task, 'project', None), 'project_id', None)
    if not project_id:
        return {
            'status': 'SCOPE_DISABLED', 'context': '', 'selected_ids': [],
            'provider': 'V1', 'delivery_approved': False, 'delivered': False,
        }
    return _compile_project_scoped_v1(
        vault, project_id, budget=budget, human_approval=human_approval,
        prompt=prompt, provider_config_path=provider_config_path,
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
