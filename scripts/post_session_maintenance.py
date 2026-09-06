#!/usr/bin/env python3
"""
Brain-Eleven v3 - Post-Session Maintenance (Phase 12)

Single entry point session-end.sh calls to run everything Phase 10/11
built that the daily hook pipeline never touched: knowledge graph rebuild,
anomaly detection, and a same-day digest. Writes one compact report file
that session-start.sh reads to actually surface findings to the user,
instead of them sitting silently in files nobody looks at.

Design constraints (this runs inside a shell hook on every session end):
- MUST NOT raise. A bug here must never block session end the way a
  compiler/validator failure wouldn't either - every step is wrapped so
  one failing step still lets the others run and still produces a report.
- MUST be fast and idempotent - session-end can fire more than once a day,
  and entity_extractor.build_graph() already does a full rebuild each call.
- MUST NOT require the REST API process (search-api.py) to be running -
  this is a CLI-only maintenance step, same as memory-validator.py itself.
"""

import json
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, Any

SCRIPTS_DIR = Path(__file__).parent
REPO_ROOT = SCRIPTS_DIR.resolve().parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(SCRIPTS_DIR))

from brain_eleven.support import (  # noqa: E402
    AnomalyDetector,
    MemorySummarizer,
    setup_logging,
)
from brain_eleven.extraction import EntityExtractor  # noqa: E402
from memory_store import MemoryStore, MemoryStoreError  # noqa: E402

logger = setup_logging(__name__)

# Anomaly counts at or above this many warning-or-worse findings get
# surfaced at the next session start rather than silently logged.
SURFACE_THRESHOLD = 1


def _run_step(name: str, fn) -> Dict[str, Any]:
    """Run one maintenance step, catching everything so the others still run."""
    try:
        result = fn()
        return {"ok": True, "data": result}
    except Exception as e:
        logger.error(f"Maintenance step '{name}' failed: {e}")
        return {"ok": False, "error": str(e)}


def run_maintenance(vault_path: str = ".", generated_by_run: str = None) -> Dict[str, Any]:
    """Run graph rebuild + anomaly detection + same-day digest, return a report dict."""
    graph_step = _run_step(
        "graph_rebuild",
        lambda: EntityExtractor(vault_path).build_graph().stats(),
    )
    anomaly_step = _run_step(
        "anomaly_detection",
        lambda: AnomalyDetector(vault_path).detect_all(),
    )
    digest_step = _run_step(
        "digest",
        lambda: MemorySummarizer(vault_path).generate_digest(days=1, top_n_per_type=3),
    )

    anomaly_report = anomaly_step["data"] if anomaly_step["ok"] else None
    should_surface = bool(
        anomaly_report and anomaly_report.get("total_anomalies", 0) >= SURFACE_THRESHOLD
    )

    try:
        source_memory_revision = MemoryStore(vault_path).revision()
    except MemoryStoreError as exc:
        source_memory_revision = None
        logger.error(f"Could not read canonical revision for maintenance report: {exc}")

    report = {
        "generated_at": datetime.now().isoformat(),
        "generated_by_run": generated_by_run,
        "source_memory_revision": source_memory_revision,
        "graph": graph_step,
        "anomalies": anomaly_step,
        "digest": digest_step,
        "surface_at_next_session": should_surface,
    }
    return report


def save_report(report: Dict[str, Any], vault_path: str = ".") -> Path:
    """Write the report to .claude/session-maintenance-report.json (atomic)."""
    claude_dir = Path(vault_path) / ".claude"
    claude_dir.mkdir(exist_ok=True)
    report_file = claude_dir / "session-maintenance-report.json"

    tmp_path = report_file.with_suffix(".tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    tmp_path.replace(report_file)

    return report_file


def summarize_for_shell(report: Dict[str, Any]) -> str:
    """One-line-per-step plaintext summary for the hook's log/echo output."""
    lines = []

    graph = report["graph"]
    if graph["ok"]:
        stats = graph["data"]
        lines.append(f"Graph: OK ({stats['total_entities']} entities, {stats['total_relationships']} relationships)")
    else:
        lines.append("Graph: FAILED")

    anomalies = report["anomalies"]
    if anomalies["ok"]:
        count = anomalies["data"]["total_anomalies"]
        lines.append(f"Anomalies: OK ({count} found)" if count else "Anomalies: OK (clean)")
    else:
        lines.append("Anomalies: FAILED")

    digest = report["digest"]
    if digest["ok"]:
        considered = digest["data"]["total_memories_considered"]
        lines.append(f"Digest: OK ({considered} memories today)")
    else:
        lines.append("Digest: FAILED")

    return "\n".join(lines)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run Brain-Eleven post-session maintenance")
    parser.add_argument("--vault", default=".", help="Path to vault root")
    parser.add_argument("--quiet", action="store_true", help="Suppress the shell summary print")
    parser.add_argument("--generated-by-run", default=None)
    args = parser.parse_args()

    result = run_maintenance(args.vault, generated_by_run=args.generated_by_run)
    save_report(result, args.vault)

    if not args.quiet:
        print(summarize_for_shell(result))

    # Always exit 0: this is best-effort maintenance, not a gate on session end.
    sys.exit(0)
