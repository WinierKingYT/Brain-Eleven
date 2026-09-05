"""CLI for local-only real-use annotations and derived usage telemetry."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from .contracts import PrivateEvaluationCase, PrivateEvaluationError, evaluate_case, load_case, write_case
from .usage import UsageTelemetryError, UsageTelemetryStore


def _json(document: object) -> None:
    print(json.dumps(document, ensure_ascii=False, sort_keys=True, indent=2))


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Local-only, content-free real-use evaluation tools")
    subparsers = parser.add_subparsers(dest="command", required=True)

    annotate = subparsers.add_parser("annotate", help="add or replace one memory label")
    annotate.add_argument("--path", required=True, type=Path)
    annotate.add_argument("--memory-id", required=True)
    annotate.add_argument("--label", required=True, choices=("required", "helpful", "noise", "forbidden"))
    annotate.add_argument("--case-id")
    annotate.add_argument("--task-id")
    annotate.add_argument("--project-id")

    score = subparsers.add_parser("score", help="score a private case using IDs only")
    score.add_argument("--path", required=True, type=Path)
    score.add_argument("--selected-id", action="append", default=[])

    validate = subparsers.add_parser("validate", help="validate private JSON cases without printing content")
    validate.add_argument("--root", type=Path, default=Path("evals/private"))

    usage = subparsers.add_parser("usage", help="record one observable, non-authoritative usage event")
    usage.add_argument("--vault", type=Path, default=Path("."))
    usage.add_argument("--memory-id", required=True)
    usage.add_argument("--event", required=True, choices=("retrieved", "selected", "rendered", "explicit_reference", "user_helpful", "user_unhelpful", "contradiction"))

    args = parser.parse_args(argv)
    try:
        if args.command == "annotate":
            if args.path.exists():
                case = load_case(args.path)
            else:
                if not args.case_id or not args.task_id:
                    raise PrivateEvaluationError("new annotation files require --case-id and --task-id")
                case = PrivateEvaluationCase.empty(args.case_id, args.task_id, args.project_id)
            updated = case.with_annotation(args.memory_id, args.label)
            _json({"path": str(write_case(updated, args.path)), "case_id": updated.case_id, "annotation_count": len(updated.annotations)})
            return 0
        if args.command == "score":
            _json(evaluate_case(load_case(args.path), args.selected_id or None))
            return 0
        if args.command == "validate":
            files = sorted(args.root.glob("**/*.json")) if args.root.exists() else []
            cases = [load_case(path, private_root=args.root) for path in files]
            if len({case.case_id for case in cases}) != len(cases):
                raise PrivateEvaluationError("private case IDs must be unique")
            _json({"valid": True, "case_count": len(cases), "root": str(args.root)})
            return 0
        result = UsageTelemetryStore(args.vault).record(args.memory_id, args.event)
        _json({"recorded": True, "memory_count": len(result["memory"])})
        return 0
    except (PrivateEvaluationError, UsageTelemetryError, OSError) as exc:
        _json({"valid": False, "error": type(exc).__name__})
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
