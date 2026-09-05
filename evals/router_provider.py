"""Phase 17 provider adapter for the unchanged Phase 15 selection evaluator."""

from __future__ import annotations

import sys
from pathlib import Path

from context_router import ContextRouter, RoutingOptions

from .contracts import NormalizedEvaluationResult, SelectedContextItem
from .schema import GoldenTask


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from memory_store import MemoryStore  # noqa: E402
from brain_eleven.projects.registry import ProjectRegistry  # noqa: E402
from state_resolver import STATE_NOT_FOUND, StateResolver  # noqa: E402
from state_store import StateService  # noqa: E402
from task_state_context import TaskStateComposer  # noqa: E402


ROUTER_PROVIDER_ID = "task_aware_router_v1"
ROUTER_CAPABILITIES = {
    "scope_isolation": "supported",
    "lifecycle_filtering": "supported",
    "task_aware_ranking": "supported",
    "authority_resolution": "unsupported",
    "conflict_resolution": "unsupported",
}
_SOURCE = {"type": "system", "reference": "phase17_evaluation"}


class RouterEvaluationAdapterError(RuntimeError):
    """A router result cannot be normalized into the independent eval contract."""


class RouterContextProvider:
    """Run the read-only router and rehydrate only synthetic evaluation records."""

    provider_id = ROUTER_PROVIDER_ID

    @staticmethod
    def _ensure_project(vault: Path, project_id: str) -> Path:
        root = vault / "router-projects" / project_id
        registry = ProjectRegistry(vault)
        registry.register(root, project_id=project_id)
        if StateResolver(vault).resolve(project_id).status == STATE_NOT_FOUND:
            StateService(vault).init_project(project_id, source=_SOURCE)
        return root

    def select(self, task: GoldenTask, vault_path: Path | str) -> NormalizedEvaluationResult:
        vault = Path(vault_path)
        if not vault.is_dir():
            raise RouterEvaluationAdapterError(f"evaluation vault must be a directory: {vault}")
        if task.project_id is None:
            context = TaskStateComposer(vault, vault / "router-global").compose(task.prompt)
            options = RoutingOptions(scope_mode="GLOBAL_ONLY")
        else:
            root = self._ensure_project(vault, task.project_id)
            context = TaskStateComposer(vault, root).compose(task.prompt)
            options = RoutingOptions()
        result = ContextRouter(vault).route(context, options)
        if result.status not in {"SUCCESS", "DEGRADED", "EMPTY"}:
            raise RouterEvaluationAdapterError(f"router failed for {task.task_id}: {result.status}: {result.error}")
        revision = result.input_revisions.get("memory")
        if isinstance(revision, bool) or not isinstance(revision, int) or revision < 0:
            raise RouterEvaluationAdapterError("router did not provide a valid memory revision")
        records = {
            record.get("memory_id"): record
            for record in MemoryStore(vault).load().get("validated_memory", [])
            if isinstance(record, dict) and record.get("memory_id")
        }
        selected = []
        for candidate in result.candidates:
            if candidate.source_type != "memory":
                continue
            record = records.get(candidate.candidate_id)
            if record is None:
                raise RouterEvaluationAdapterError(f"router returned unknown memory: {candidate.candidate_id}")
            selected.append(
                SelectedContextItem(
                    id=candidate.candidate_id,
                    source_type="memory",
                    project_id=record.get("project_id") or None,
                    memory_type=record["type"],
                    status=record["status"],
                    content=record["content"],
                    score=candidate.retrieval_score,
                )
            )
        return NormalizedEvaluationResult(
            task_id=task.task_id,
            provider_id=self.provider_id,
            selected_items=tuple(selected),
            source_memory_revision=revision,
            project_id=task.project_id,
            retrieval_scope="default" if task.project_id is not None else "global",
            capabilities=ROUTER_CAPABILITIES,
        )
