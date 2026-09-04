"""Phase 19 CLI: compile supplied contracts or run an explicit shadow chain."""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Mapping

from context_router import RoutingOptions

from .compiler import ContextCompilerV2
from .models import BudgetContract, CompilationOptions
from .serialization import compilation_request_from_dict
from .shadow import CompilerShadowRunner


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Cannot read JSON input: {path}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"JSON input must be an object: {path}")
    return value


def _atomic_write(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".compiler-v2-", suffix=".json", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        Path(temporary).replace(path)
    finally:
        if Path(temporary).exists():
            Path(temporary).unlink()


def _emit(bundle, *, as_json: bool, manifest_only: bool) -> None:
    payload = bundle.manifest_dict() if manifest_only else bundle.to_dict()
    if as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    print(f"STATUS: {bundle.status}")
    print(f"PROFILE: {bundle.compiler_profile}")
    print(f"SELECTED: {len(bundle.selected)}")
    print(f"ESTIMATED TOKENS: {bundle.budget.get('estimated_tokens', 0)}")
    if bundle.error:
        print(f"ERROR: {bundle.error}")


def _compile(args: argparse.Namespace) -> int:
    try:
        request = compilation_request_from_dict(_load_json(args.request_file))
        bundle = ContextCompilerV2(args.vault).compile(
            request, CompilationOptions(mode=args.mode.upper(), allow_history=args.allow_history)
        )
    except ValueError as exc:
        print(json.dumps({"error": {"code": "INVALID_INPUT", "message": str(exc)}}))
        return 2
    if args.output:
        _atomic_write(args.output, bundle.to_dict() if not args.manifest_only else bundle.manifest_dict())
    _emit(bundle, as_json=args.json, manifest_only=args.manifest_only)
    return 0 if bundle.status in {"SUCCESS", "DEGRADED", "EMPTY"} else 2


def _shadow(args: argparse.Namespace) -> int:
    try:
        routing = RoutingOptions(
            scope_mode="CURRENT_PROJECT", include_global=not args.no_global,
            history_mode="ACTIVE_PLUS_RELEVANT_HISTORY" if args.allow_history else "ACTIVE_ONLY",
        )
        budget = BudgetContract(args.max_context_tokens, args.minimum_headroom_tokens, args.hard_byte_limit)
        router, authority, bundle = CompilerShadowRunner(args.vault, args.project_root).run(args.request, budget, routing)
    except ValueError as exc:
        print(json.dumps({"error": {"code": "INVALID_INPUT", "message": str(exc)}}))
        return 2
    if args.shadow_report:
        _atomic_write(args.shadow_report, CompilerShadowRunner.report(router, authority, bundle))
    _emit(bundle, as_json=args.json, manifest_only=args.manifest_only)
    return 0 if bundle.status in {"SUCCESS", "DEGRADED", "EMPTY"} else 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compile Phase 18 resolution into bounded task context")
    commands = parser.add_subparsers(dest="command", required=True)
    compile_command = commands.add_parser("compile", help="Compile supplied TaskState/Resolution JSON")
    compile_command.add_argument("--vault", default=".")
    compile_command.add_argument("--request-file", type=Path, required=True)
    compile_command.add_argument("--mode", choices=("off", "shadow"), default="shadow")
    compile_command.add_argument("--allow-history", action="store_true")
    compile_command.add_argument("--output", type=Path)
    compile_command.add_argument("--manifest-only", action="store_true")
    compile_command.add_argument("--json", action="store_true")
    shadow = commands.add_parser("shadow", help="Run task/state → route → authority → compiler without injection")
    shadow.add_argument("--vault", default=".")
    shadow.add_argument("--project-root", default=".")
    shadow.add_argument("--request", required=True)
    shadow.add_argument("--max-context-tokens", type=int, default=2048)
    shadow.add_argument("--minimum-headroom-tokens", type=int, default=128)
    shadow.add_argument("--hard-byte-limit", type=int, default=24_000)
    shadow.add_argument("--no-global", action="store_true")
    shadow.add_argument("--allow-history", action="store_true")
    shadow.add_argument("--shadow-report", type=Path)
    shadow.add_argument("--manifest-only", action="store_true")
    shadow.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    return _compile(args) if args.command == "compile" else _shadow(args)


if __name__ == "__main__":
    raise SystemExit(main())
