"""Content-safe command line surface for Phase 18 authority shadowing."""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from pathlib import Path

from context_router import RoutingOptions

from .models import AuthorityOptions
from .resolver import AuthorityResolver
from .serialization import router_result_from_dict, task_state_from_dict
from .shadow import AuthorityShadowRunner


def _load_json(path: Path) -> dict:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Cannot read JSON input: {path}") from exc
    if not isinstance(document, dict):
        raise ValueError(f"JSON input must be an object: {path}")
    return document


def _atomic_write(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".authority-shadow-", suffix=".json", dir=path.parent)
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


def _scope(args: argparse.Namespace) -> tuple[str, tuple[str, ...]]:
    mode = {"current": "CURRENT_PROJECT", "global": "GLOBAL_ONLY", "selected": "SELECTED_PROJECTS"}[args.scope]
    projects = tuple(args.project)
    return mode, projects


def _print_result(result, explain: bool, as_json: bool) -> None:
    payload = result.to_dict()
    if as_json:
        if not explain:
            payload.pop("ledger", None)
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    print(f"STATUS: {result.status}")
    print(f"CANDIDATES: {len(result.candidates)}")
    print(f"CONFLICTS: {len(result.conflict_sets)}")
    if result.degraded_reasons:
        print("DEGRADED: " + ", ".join(result.degraded_reasons))
    if result.error:
        print("ERROR: " + result.error)
    if explain:
        for entry in result.ledger:
            print(f"- {','.join(entry.subject_ids)} [{entry.action}; {entry.code}]")


def _resolve(args: argparse.Namespace) -> int:
    try:
        task_state = task_state_from_dict(_load_json(args.task_state))
        router_result = router_result_from_dict(_load_json(args.router_result))
        scope_mode, projects = _scope(args)
        options = AuthorityOptions(
            scope_mode=scope_mode,
            selected_project_ids=projects,
            include_global=not args.no_global,
            history_mode={"active": "ACTIVE_ONLY", "relevant": "ACTIVE_PLUS_RELEVANT_HISTORY", "only": "HISTORY_ONLY"}[args.history],
            mode=args.mode.upper(),
        )
        result = AuthorityResolver(args.vault).resolve(task_state, router_result, options)
    except ValueError as exc:
        print(json.dumps({"error": {"code": "INVALID_INPUT", "message": str(exc)}}))
        return 2
    _print_result(result, args.explain, args.json)
    return 0 if result.status in {"SUCCESS", "DEGRADED", "EMPTY"} else 2


def _shadow(args: argparse.Namespace) -> int:
    try:
        scope_mode, projects = _scope(args)
        routing = RoutingOptions(
            scope_mode=scope_mode,
            selected_project_ids=projects,
            include_global=not args.no_global,
            history_mode={"active": "ACTIVE_ONLY", "relevant": "ACTIVE_PLUS_RELEVANT_HISTORY", "only": "HISTORY_ONLY"}[args.history],
            allow_archived_history=args.allow_archived_history,
            mode=args.mode.upper(),
        )
        router_result, result = AuthorityShadowRunner(args.vault, args.project_root).run(args.request, routing)
        if args.shadow_report:
            _atomic_write(args.shadow_report, AuthorityShadowRunner.report(router_result, result))
    except ValueError as exc:
        print(json.dumps({"error": {"code": "INVALID_INPUT", "message": str(exc)}}))
        return 2
    _print_result(result, args.explain, args.json)
    return 0 if result.status in {"SUCCESS", "DEGRADED", "EMPTY"} else 2


def _common_options(parser: argparse.ArgumentParser, *, request: bool) -> None:
    parser.add_argument("--vault", default=".")
    if request:
        parser.add_argument("--project-root", default=".")
        parser.add_argument("--request", required=True)
        parser.add_argument("--shadow-report", type=Path)
        parser.add_argument("--allow-archived-history", action="store_true")
    parser.add_argument("--scope", choices=("current", "global", "selected"), default="current")
    parser.add_argument("--project", action="append", default=[])
    parser.add_argument("--no-global", action="store_true")
    parser.add_argument("--history", choices=("active", "relevant", "only"), default="active")
    parser.add_argument("--mode", choices=("off", "shadow"), default="shadow")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--explain", action="store_true")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Resolve Phase 18 authority without content output")
    commands = parser.add_subparsers(dest="command", required=True)
    resolve = commands.add_parser("resolve", help="Resolve supplied TaskStateContext and RouterResult JSON")
    resolve.add_argument("--task-state", type=Path, required=True)
    resolve.add_argument("--router-result", type=Path, required=True)
    _common_options(resolve, request=False)
    shadow = commands.add_parser("shadow", help="Compose, route, and resolve in OFF/SHADOW mode")
    _common_options(shadow, request=True)
    args = parser.parse_args(argv)
    return _resolve(args) if args.command == "resolve" else _shadow(args)


if __name__ == "__main__":
    raise SystemExit(main())
