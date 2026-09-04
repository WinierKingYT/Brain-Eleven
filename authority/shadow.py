"""Read-only OFF/SHADOW coordinator for one route-to-authority pass."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from context_router import ContextRouter, RoutingOptions

from .config import AuthorityConfig
from .models import AuthorityOptions, ResolutionResult
from .resolver import AuthorityResolver


_ROOT = Path(__file__).resolve().parents[1]
_SCRIPTS = _ROOT / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from task_state_context import TaskStateComposer  # noqa: E402


class AuthorityShadowRunner:
    """Run at most one explicit route→resolve retry without production injection."""

    def __init__(self, vault_path: str | Path, project_root: str | Path):
        self.vault_path = Path(vault_path)
        self.project_root = Path(project_root)

    @staticmethod
    def _authority_options(options: RoutingOptions) -> AuthorityOptions:
        return AuthorityOptions(
            scope_mode=options.scope_mode,
            selected_project_ids=options.selected_project_ids,
            include_global=options.include_global,
            history_mode=options.history_mode,
            mode=options.mode,
        )

    def run(self, request: str, options: RoutingOptions | None = None) -> tuple[Any, ResolutionResult]:
        routing = options or RoutingOptions()
        config = AuthorityConfig.load(self.vault_path)
        attempts = config.shadow_retry_on_stale + 1
        router_result = None
        resolution = None
        for _ in range(attempts):
            context = TaskStateComposer(self.vault_path, self.project_root).compose(request)
            router_result = ContextRouter(self.vault_path).route(context, routing)
            resolution = AuthorityResolver(self.vault_path).resolve(
                context, router_result, self._authority_options(routing)
            )
            if resolution.status != "STALE_INPUT":
                break
        assert router_result is not None and resolution is not None
        return router_result, resolution

    @staticmethod
    def report(router_result: Any, resolution: ResolutionResult) -> dict[str, Any]:
        """Return a durable-report-safe summary with no memory/state text."""
        return {
            "router": {
                "status": router_result.status,
                "candidate_ids": [candidate.candidate_id for candidate in router_result.candidates],
                "input_revisions": dict(router_result.input_revisions),
            },
            "authority": resolution.to_dict(),
        }
