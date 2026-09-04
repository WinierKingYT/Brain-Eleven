"""Explicit non-injecting orchestration for Phase 19 shadow evaluation."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Mapping

from authority import AuthorityOptions, AuthorityResolver
from context_router import ContextRouter, RoutingOptions

from .compiler import ContextCompilerV2
from .models import BudgetContract, CompilationOptions, CompilationRequest, ContextBundle


_ROOT = Path(__file__).resolve().parents[1]
_SCRIPTS = _ROOT / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))


class CompilerShadowRunner:
    """Compose → route → resolve → compile without touching SessionStart or V1."""

    def __init__(self, vault_path: str | Path, project_root: str | Path):
        self.vault_path = Path(vault_path)
        self.project_root = Path(project_root)

    def run(self, request_text: str, budget: BudgetContract, routing: RoutingOptions | None = None) -> tuple[Any, Any, ContextBundle]:
        from task_state_context import TaskStateComposer

        routing = routing or RoutingOptions()
        task_state = TaskStateComposer(self.vault_path, self.project_root).compose(request_text)
        router = ContextRouter(self.vault_path).route(task_state, routing)
        authority = AuthorityResolver(self.vault_path).resolve(
            task_state,
            router,
            AuthorityOptions(
                scope_mode=routing.scope_mode,
                selected_project_ids=routing.selected_project_ids,
                include_global=routing.include_global,
                history_mode=routing.history_mode,
                mode=routing.mode,
            ),
        )
        bundle = ContextCompilerV2(self.vault_path).compile(
            CompilationRequest(task_state, authority, budget), CompilationOptions(mode="SHADOW")
        )
        return router, authority, bundle

    @staticmethod
    def report(router_result: Any, authority_result: Any, bundle: ContextBundle) -> Mapping[str, Any]:
        """Content-free shadow comparison suitable for CI artifacts."""
        return {
            "schema_version": 1,
            "rollout_mode": "SHADOW",
            "context_injection": False,
            "router": {"status": router_result.status, "candidate_count": len(router_result.candidates)},
            "authority": {"status": authority_result.status, "candidate_count": len(authority_result.candidates)},
            "compiler": bundle.manifest_dict(),
        }
