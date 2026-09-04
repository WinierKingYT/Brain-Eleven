"""Phase 19 adapter into the unchanged Phase 15 selection evaluation contract."""

from __future__ import annotations

import sys
from pathlib import Path

from authority import AuthorityOptions, AuthorityResolver
from context_compiler_v2 import BudgetContract, CompilationRequest, ContextCompilerV2
from context_router import ContextRouter, RoutingOptions

from .contracts import NormalizedEvaluationResult, SelectedContextItem
from .router_provider import RouterContextProvider
from .schema import GoldenTask


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from memory_store import MemoryStore  # noqa: E402
from task_state_context import TaskStateComposer  # noqa: E402


COMPILER_PROVIDER_ID = "context_compiler_v2"
COMPILER_CAPABILITIES = {
    "scope_isolation": "supported",
    "lifecycle_filtering": "supported",
    "task_aware_ranking": "supported",
    "authority_resolution": "supported",
    "conflict_resolution": "supported",
    "token_budgeting": "supported",
}


class CompilerV2ContextProvider:
    """Evaluate final selected memory references; fixture content stays in eval only."""

    provider_id = COMPILER_PROVIDER_ID

    def select(self, task: GoldenTask, vault_path: Path | str) -> NormalizedEvaluationResult:
        vault = Path(vault_path)
        if task.project_id is None:
            context = TaskStateComposer(vault, vault / "compiler-v2-global").compose(task.prompt)
            routing = RoutingOptions(scope_mode="GLOBAL_ONLY")
        else:
            root = RouterContextProvider._ensure_project(vault, task.project_id)
            context = TaskStateComposer(vault, root).compose(task.prompt)
            routing = RoutingOptions()
        router = ContextRouter(vault).route(context, routing)
        authority = AuthorityResolver(vault).resolve(
            context, router,
            AuthorityOptions(
                scope_mode=routing.scope_mode, selected_project_ids=routing.selected_project_ids,
                include_global=routing.include_global, history_mode=routing.history_mode,
            ),
        )
        bundle = ContextCompilerV2(vault).compile(
            CompilationRequest(context, authority, BudgetContract(2048, minimum_headroom_tokens=128))
        )
        if bundle.status not in {"SUCCESS", "DEGRADED", "EMPTY"}:
            raise RuntimeError(f"compiler v2 failed for {task.task_id}: {bundle.status}: {bundle.error}")
        records = {
            record.get("memory_id"): record
            for record in MemoryStore(vault).load().get("validated_memory", [])
            if isinstance(record, dict) and record.get("memory_id")
        }
        selected = []
        for item in bundle.selected:
            if item.source_type != "memory":
                continue
            record = records.get(item.candidate_id)
            if record is None:
                raise RuntimeError(f"compiler returned unknown memory: {item.candidate_id}")
            selected.append(
                SelectedContextItem(
                    id=item.candidate_id, source_type="memory", project_id=record.get("project_id") or None,
                    memory_type=record["type"], status=record["status"], content=record["content"], score=0.0,
                )
            )
        revision = bundle.input_revisions.get("memory")
        if isinstance(revision, bool) or not isinstance(revision, int):
            raise RuntimeError("compiler did not supply a valid memory revision")
        return NormalizedEvaluationResult(
            task_id=task.task_id, provider_id=self.provider_id, selected_items=tuple(selected),
            source_memory_revision=revision, project_id=task.project_id,
            retrieval_scope="default" if task.project_id is not None else "global",
            capabilities=COMPILER_CAPABILITIES,
        )
