"""Local diagnostic CLI for content-safe Phase 17 shadow routing."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_SCRIPTS = _ROOT / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from task_state_context import TaskStateComposer  # noqa: E402

from .models import RoutingOptions
from .router import ContextRouter


def _atomic_write(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".router-shadow-", suffix=".json", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        Path(temporary).replace(path)
    finally:
        candidate = Path(temporary)
        if candidate.exists():
            candidate.unlink()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run a content-safe Phase 17 router shadow route")
    parser.add_argument("route", nargs="?")
    parser.add_argument("--vault", default=".")
    parser.add_argument("--project-root", default=".")
    parser.add_argument("--request", required=True)
    parser.add_argument("--scope", choices=("current", "global", "selected"), default="current")
    parser.add_argument("--project", action="append", default=[])
    parser.add_argument("--history", choices=("active", "relevant", "only"), default="active")
    parser.add_argument("--allow-archived-history", action="store_true")
    parser.add_argument("--mode", choices=("off", "shadow"), default="shadow")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--explain", action="store_true")
    parser.add_argument("--shadow-report", type=Path)
    args = parser.parse_args(argv)

    scope = {"current": "CURRENT_PROJECT", "global": "GLOBAL_ONLY", "selected": "SELECTED_PROJECTS"}[args.scope]
    history = {"active": "ACTIVE_ONLY", "relevant": "ACTIVE_PLUS_RELEVANT_HISTORY", "only": "HISTORY_ONLY"}[args.history]
    options = RoutingOptions(
        scope_mode=scope,
        selected_project_ids=tuple(args.project),
        history_mode=history,
        allow_archived_history=args.allow_archived_history,
        mode=args.mode.upper(),
    )
    context = TaskStateComposer(args.vault, args.project_root).compose(args.request)
    result = ContextRouter(args.vault).route(context, options)
    payload = result.to_dict()
    if args.shadow_report:
        _atomic_write(args.shadow_report, payload)
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        plan = result.plan
        print(f"STATUS: {result.status}")
        if plan:
            print(f"PROFILE: {plan.route_profile}")
            print(f"SCOPE: {plan.scope.mode} ({', '.join(plan.scope.project_ids) or 'global'})")
            print(f"QUERIES: {len(plan.queries)}")
        print(f"CANDIDATES: {len(result.candidates)}")
        if args.explain:
            for candidate in result.candidates:
                print(
                    "- "
                    f"{candidate.candidate_id} "
                    f"[{candidate.source_type}/{candidate.content_type}; "
                    f"score={candidate.retrieval_score:.2f}; "
                    f"signals={','.join(candidate.match_signals)}]"
                )
        if result.degraded_reasons:
            print("DEGRADED: " + ", ".join(result.degraded_reasons))
        if result.error:
            print("ERROR: " + result.error)
    return 0 if result.status in {"SUCCESS", "DEGRADED", "EMPTY"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
