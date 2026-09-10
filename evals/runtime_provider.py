"""PRE-13 provider runs the very same read-only chain used by native hooks."""
from pathlib import Path
from brain_eleven.runtime.context import compile_task
from brain_eleven.memory import MemoryStore
from context_router import RoutingOptions
from scripts.task_state_context import TaskStateComposer
from .contracts import NormalizedEvaluationResult, SelectedContextItem
from .router_provider import RouterContextProvider
from .compiler_v2_provider import COMPILER_CAPABILITIES


class RuntimeContextProvider:
    provider_id = 'pre13_runtime'

    def __init__(self, budget=2048):
        self.budget = budget
        self.last_result = None

    def select(self, task, vault_path):
        vault = Path(vault_path)
        root = RouterContextProvider._ensure_project(vault, task.project_id) if task.project_id else vault / 'runtime-global'
        context = TaskStateComposer(vault, root).compose(task.prompt)
        result = compile_task(vault, context, routing=RoutingOptions(scope_mode='CURRENT_PROJECT' if task.project_id else 'GLOBAL_ONLY'), budget=self.budget)
        self.last_result = result
        if result['status'] not in {'SUCCESS', 'DEGRADED', 'EMPTY'}:
            raise RuntimeError('Runtime context failed: ' + result['status'])
        document = MemoryStore(vault).load()
        records = {x['memory_id']: x for x in document['validated_memory']}
        selected = tuple(SelectedContextItem(id=key, source_type='memory', project_id=records[key].get('project_id') or None,
                         memory_type=records[key]['type'], status=records[key]['status'], content=records[key]['content'], score=0)
                         for key in result['selected_ids'] if key in records)
        return NormalizedEvaluationResult(task_id=task.task_id, provider_id=self.provider_id, selected_items=selected,
                   source_memory_revision=document['revision'], project_id=task.project_id,
                   retrieval_scope='default' if task.project_id else 'global', capabilities=COMPILER_CAPABILITIES)
