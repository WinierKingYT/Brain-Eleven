#!/usr/bin/env python3
"""Read-only CAPTURE_SILENT_GAP audit over real sessions.

Compares an independent denominator -- the native Claude Code transcript
files under ``~/.claude/projects/<slug>/<session_id>.jsonl`` for every
registered project -- against the capture ledger
(``.brain-eleven/capture/capture-ledger.jsonl``). A session that has a
transcript but no ``ENQUEUED`` SessionEnd in the ledger is a silent gap; a
session whose capture ended in ``DEAD_LETTER`` is a loss.

The audit never writes, never reads message content (only file names and
the ledger's hashes/codes), and prints no raw paths or session ids.

Gate (roadmap step 1): at least ``--min-projects`` projects and
``--min-sessions`` audited sessions, zero missing enqueues, zero dead
letters.

It also joins each session's SessionStart delivery receipt
(``.brain-eleven/runtime/deliveries``) so one report shows captured ->
compiled -> delivered per session (``bootstrap_receipts``: DELIVERED,
COMPILED_NOT_DELIVERED:<reason>, NOT_COMPILED:<reason>, NO_RECEIPT). The
receipts are reported, not gated: SHADOW legitimately delivers nothing. Exit code 0 = PASS, 1 = FAIL, 2 = INSUFFICIENT_EVIDENCE.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from brain_eleven.runtime.ownership import _project_slug  # noqa: E402
from brain_eleven.runtime.worker import capture_session_hash  # noqa: E402

# The capture queue's own event type for native Stop/SessionEnd captures.
SESSION_END = "SESSION_END"


def _parse_since(value: Optional[str]) -> Optional[float]:
    if not value:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.timestamp()


def load_registry(vault: Path) -> list[dict[str, Any]]:
    path = vault / ".claude" / "project-registry.json"
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    projects = document.get("projects") if isinstance(document, dict) else None
    return [p for p in projects or [] if isinstance(p, dict) and p.get("project_id") and p.get("root")]


def load_ledger(vault: Path) -> Iterable[dict[str, Any]]:
    path = vault / ".brain-eleven" / "capture" / "capture-ledger.jsonl"
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    records = []
    for line in lines:
        try:
            record = json.loads(line)
        except ValueError:
            continue
        if isinstance(record, dict):
            records.append(record)
    return records


def load_bootstrap_receipts(vault: Path) -> dict[str, dict[str, Any]]:
    """capture_session_hash -> latest SessionStart delivery receipt."""
    receipts: dict[str, dict[str, Any]] = {}
    for path in (vault / ".brain-eleven" / "runtime" / "deliveries").glob("*.json"):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(record, dict) or record.get("event") != "SessionStart":
            continue
        key = record.get("capture_session_hash")
        if isinstance(key, str) and str(record.get("at", "")) >= str(receipts.get(key, {}).get("at", "")):
            receipts[key] = record
    return receipts


def audit(vault: Path, claude_home: Path, *, since: Optional[float] = None) -> dict[str, Any]:
    # session_id_hash -> set of ledger actions / error codes, SessionEnd only.
    actions: dict[str, set[str]] = defaultdict(set)
    errors: dict[str, set[str]] = defaultdict(set)
    ledger_projects: dict[str, str] = {}
    for record in load_ledger(vault):
        if record.get("event_type") != SESSION_END:
            continue
        key = record.get("session_id_hash")
        if not isinstance(key, str):
            continue
        actions[key].add(str(record.get("action")))
        if record.get("error_code"):
            errors[key].add(str(record["error_code"]))
        if record.get("project_id"):
            ledger_projects[key] = str(record["project_id"])

    receipts = load_bootstrap_receipts(vault)
    bootstrap: dict[str, int] = defaultdict(int)
    projects = []
    totals = defaultdict(int)
    error_codes: dict[str, int] = defaultdict(int)
    for project in load_registry(vault):
        directory = claude_home / "projects" / _project_slug(str(project["root"]))
        row = {"project_id": project["project_id"], "transcript_dir_found": directory.is_dir(),
               "sessions": 0, "enqueued": 0, "committed": 0, "dead_letter": 0,
               "pending": 0, "missing": 0, "wrong_project": 0, "dead_letter_recovered": 0}
        transcripts = sorted(directory.glob("*.jsonl")) if row["transcript_dir_found"] else []
        for transcript in transcripts:
            try:
                if since is not None and transcript.stat().st_mtime < since:
                    continue
            except OSError:
                continue
            key = capture_session_hash("claude", transcript.stem)
            row["sessions"] += 1
            receipt = receipts.get(key)
            stage = receipt.get("stage", "UNKNOWN") if receipt else "NO_RECEIPT"
            if receipt and receipt.get("reason"):
                stage += ":" + str(receipt["reason"])
            bootstrap[stage] += 1
            seen = actions.get(key, set())
            if "ENQUEUED" not in seen and "DUPLICATE" not in seen:
                row["missing"] += 1
                continue
            row["enqueued"] += 1
            if ledger_projects.get(key) not in (None, project["project_id"]):
                row["wrong_project"] += 1
            # Every Stop enqueues its own job, so one session can have a
            # dead-lettered job and a later committed one; that is not a loss.
            if "COMMITTED" in seen:
                row["committed"] += 1
                if "DEAD_LETTER" in seen:
                    row["dead_letter_recovered"] += 1
            elif "DEAD_LETTER" in seen:
                row["dead_letter"] += 1
                for code in errors.get(key, ()):
                    error_codes[code] += 1
            else:
                row["pending"] += 1
        for field in ("sessions", "enqueued", "committed", "dead_letter", "dead_letter_recovered", "pending", "missing",
                      "wrong_project"):
            totals[field] += row[field]
        projects.append(row)

    return {"projects": projects, "totals": dict(totals), "dead_letter_error_codes": dict(error_codes),
            "bootstrap_receipts": dict(bootstrap),
            "projects_with_sessions": sum(1 for row in projects if row["sessions"] > 0)}


def verdict(report: dict[str, Any], *, min_projects: int, min_sessions: int) -> str:
    totals = report["totals"]
    if totals.get("missing") or totals.get("dead_letter") or totals.get("wrong_project"):
        return "FAIL"
    if report["projects_with_sessions"] < min_projects or totals.get("sessions", 0) < min_sessions:
        return "INSUFFICIENT_EVIDENCE"
    if totals.get("pending"):
        return "INSUFFICIENT_EVIDENCE"
    return "PASS"


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--vault", default=".")
    parser.add_argument("--claude-home", default=str(Path.home() / ".claude"))
    parser.add_argument("--since", help="ISO time; only audit transcripts modified after it")
    parser.add_argument("--min-projects", type=int, default=2)
    parser.add_argument("--min-sessions", type=int, default=20)
    args = parser.parse_args(argv)

    report = audit(Path(args.vault), Path(args.claude_home).expanduser(), since=_parse_since(args.since))
    report["verdict"] = verdict(report, min_projects=args.min_projects, min_sessions=args.min_sessions)
    report["gate"] = {"min_projects": args.min_projects, "min_sessions": args.min_sessions}
    print(json.dumps(report, indent=2, sort_keys=True))
    return {"PASS": 0, "FAIL": 1}.get(report["verdict"], 2)


if __name__ == "__main__":
    raise SystemExit(main())
