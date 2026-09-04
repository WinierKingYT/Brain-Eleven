"""Phase 18 adapter into the unchanged Phase 15 selection-evaluation contract."""

from __future__ import annotations

import sys
from pathlib import Path

from authority import AuthorityOptions, AuthorityResolver
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


AUTHORITY_PROVIDER_ID = "metadata_authority_v1"
AUTHORITY_CAPABILITIES = {
    "scope_isolation": "supported",
    "lifecycle_filtering": "supported",
    "task_aware_ranking": "unsupported",
    "authority_resolution": "supported",
    "conflict_resolution": "supported",
}


class AuthorityContextProvider:
    """Evaluate content-free authority output; fixture text is rehydrated only here."""

    provider_id = AUTHORITY_PROVIDER_ID

    def select(self, task: GoldenTask, vault_path: Path | str) -> NormalizedEvaluationResult:
        vault = Path(vault_path)
        if task.project_id is None:
            context = TaskStateComposer(vault, vault / "authority-global").compose(task.prompt)
            routing = RoutingOptions(scope_mode="GLOBAL_ONLY")
        else:
            root = RouterContextProvider._ensure_project(vault, task.project_id)
            context = TaskStateComposer(vault, root).compose(task.prompt)
            routing = RoutingOptions()
        router_result = ContextRouter(vault).route(context, routing)
        authority = AuthorityResolver(vault).resolve(
            context,
            router_result,
            AuthorityOptions(
                scope_mode=routing.scope_mode,
                selected_project_ids=routing.selected_project_ids,
                include_global=routing.include_global,
                history_mode=routing.history_mode,
                mode=routing.mode,
            ),
        )
        if authority.status not in {"SUCCESS", "DEGRADED", "EMPTY"}:
            raise RuntimeError(f"authority failed for {task.task_id}: {authority.status}: {authority.error}")
        revision = authority.input_revisions.get("memory")
        if isinstance(revision, bool) or not isinstance(revision, int) or revision < 0:
            raise RuntimeError("authority did not provide a valid memory revision")
        records = {
            record.get("memory_id"): record
            for record in MemoryStore(vault).load().get("validated_memory", [])
            if isinstance(record, dict) and record.get("memory_id")
        }
        selected = []
        for item in authority.candidates:
            if item.source_type != "memory" or item.status in {"SUPERSEDED", "HISTORICAL", "INVALID"}:
                continue
            record = records.get(item.candidate_id)
            if record is None:
                raise RuntimeError(f"authority returned unknown memory: {item.candidate_id}")
            selected.append(
                SelectedContextItem(
                    id=item.candidate_id,
                    source_type="memory",
                    project_id=record.get("project_id") or None,
                    memory_type=record["type"],
                    status=record["status"],
                    content=record["content"],
                    # Phase 18 has no authority score. Constant is only the
                    # legacy evaluator's required numeric placeholder.
                    score=0.0,
                )
            )
        return NormalizedEvaluationResult(
            task_id=task.task_id,
            provider_id=self.provider_id,
            selected_items=tuple(selected),
            source_memory_revision=revision,
            project_id=task.project_id,
            retrieval_scope="default" if task.project_id is not None else "global",
            capabilities=AUTHORITY_CAPABILITIES,
        )
