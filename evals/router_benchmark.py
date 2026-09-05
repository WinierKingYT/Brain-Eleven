"""Offline informational performance measurements for Phase 17 routing."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Sequence

from context_router import ContextRouter

from .corpus_builder import DEFAULT_FIXTURE_PATH
from .fixture_generator import build_vault
from .schema import load_fixture


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from brain_eleven.projects.registry import ProjectRegistry  # noqa: E402
from state_resolver import STATE_NOT_FOUND, StateResolver  # noqa: E402
from state_store import StateService  # noqa: E402
from task_state_context import TaskStateComposer  # noqa: E402


_SOURCE = {"type": "system", "reference": "phase17_benchmark"}


def _percentile(values: list[float], percentile: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    index = min(len(ordered) - 1, round((len(ordered) - 1) * percentile))
    return ordered[index]


def _prepare(vault: Path, project_id: str) -> Path:
    root = vault / "router-projects" / project_id
    ProjectRegistry(vault).register(root, project_id=project_id)
    if StateResolver(vault).resolve(project_id).status == STATE_NOT_FOUND:
        StateService(vault).init_project(project_id, source=_SOURCE)
    return root


def run_router_benchmark(*, sizes: tuple[int, ...] = (100, 1000, 10000), samples: int = 5) -> dict[str, Any]:
    """Measure deterministic route latency without imposing an absolute gate."""
    if not sizes or any(isinstance(size, bool) or not isinstance(size, int) or size < 0 for size in sizes):
        raise ValueError("sizes must be non-empty non-negative integers")
    if isinstance(samples, bool) or not isinstance(samples, int) or samples < 1:
        raise ValueError("samples must be a positive integer")
    fixture = load_fixture(DEFAULT_FIXTURE_PATH)
    results = []
    for noise_count in sorted(set(sizes)):
        with TemporaryDirectory(prefix="brain-eleven-router-benchmark-") as directory:
            vault = build_vault(fixture, Path(directory) / "vault", noise_count=noise_count).root
            (vault / ".claude" / "context-router.json").write_text(
                json.dumps({"schema_version": 1, "routing": {"cache_enabled": False}}),
                encoding="utf-8",
            )
            project_id = "eleven_capture"
            context = TaskStateComposer(vault, _prepare(vault, project_id)).compose(
                "Implement Quick Note Markdown SQLite save ordering."
            )
            router = ContextRouter(vault)
            durations = []
            for _ in range(samples):
                started = time.perf_counter()
                result = router.route(context)
                durations.append((time.perf_counter() - started) * 1000)
                if result.status not in {"SUCCESS", "DEGRADED", "EMPTY"}:
                    raise RuntimeError(f"router benchmark route failed: {result.status}")
            results.append(
                {
                    "memory_count": len(fixture.memories) + noise_count,
                    "noise_count": noise_count,
                    "samples": samples,
                    "p50_ms": round(_percentile(durations, 0.50), 3),
                    "p95_ms": round(_percentile(durations, 0.95), 3),
                }
            )
    return {
        "schema_version": 1,
        "report_type": "brain_eleven_router_benchmark",
        "offline": True,
        "hard_latency_gate": False,
        "results": results,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Benchmark Phase 17 routing without network access")
    parser.add_argument("--sizes", nargs="+", type=int, default=[100, 1000, 10000])
    parser.add_argument("--samples", type=int, default=5)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    report = run_router_benchmark(sizes=tuple(args.sizes), samples=args.samples)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
