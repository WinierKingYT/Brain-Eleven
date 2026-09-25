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
from brain_eleven.projects.registry import normalize_registry_root  # noqa: E402
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


_COUNTS = ("sessions", "enqueued", "committed", "dead_letter", "dead_letter_recovered", "pending", "missing",
           "wrong_project")


def _recent(path: Path, since: Optional[float]) -> bool:
    try:
        return since is None or path.stat().st_mtime >= since
    except OSError:
        return False


def claude_sessions(registry, claude_home: Path, since: Optional[float]) -> list[tuple[str, str, str]]:
    """Claude names each transcript ``<session_id>.jsonl`` under the project's slug."""
    found = []
    for project in registry:
        directory = claude_home / "projects" / _project_slug(str(project["root"]))
        for transcript in sorted(directory.glob("*.jsonl")) if directory.is_dir() else []:
            if _recent(transcript, since):
                found.append(("claude", project["project_id"], transcript.stem))
    return found


def _codex_meta(path: Path) -> Optional[tuple[str, str]]:
    """(session_id, cwd) from the rollout's session_meta line; reads metadata lines only."""
    try:
        with path.open("r", encoding="utf-8") as handle:
            for _, line in zip(range(20), handle):
                try:
                    document = json.loads(line)
                except ValueError:
                    continue
                if isinstance(document, dict) and document.get("type") == "session_meta":
                    payload = document.get("payload") or {}
                    session_id = payload.get("session_id") or payload.get("id")
                    cwd = payload.get("cwd")
                    if isinstance(session_id, str) and session_id and isinstance(cwd, str) and cwd:
                        return session_id, cwd
                    return None
    except (OSError, UnicodeDecodeError):
        return None
    return None


def codex_sessions(registry, codex_home: Path, since: Optional[float]) -> list[tuple[str, str, str]]:
    """Codex rollouts live under ``sessions/YYYY/MM/DD``; the project comes from session_meta.cwd."""
    roots = {}
    for project in registry:
        try:
            roots[normalize_registry_root(project["root"])] = project["project_id"]
        except (OSError, ValueError):
            continue
    found = []
    directory = codex_home / "sessions"
    for rollout in sorted(directory.rglob("*.jsonl")) if directory.is_dir() else []:
        if not _recent(rollout, since):
            continue
        meta = _codex_meta(rollout)
        if not meta:
            continue
        try:
            project_id = roots.get(normalize_registry_root(meta[1]))
        except (OSError, ValueError):
            project_id = None
        if project_id:
            found.append(("codex", project_id, meta[0]))
    return found


def audit(vault: Path, claude_home: Path, *, since: Optional[float] = None,
          codex_home: Optional[Path] = None, clients: tuple[str, ...] = ("claude",)) -> dict[str, Any]:
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
    error_codes: dict[str, int] = defaultdict(int)
    registry = load_registry(vault)
    rows: dict[tuple[str, str], dict[str, Any]] = {}
    for client in clients:
        for project in registry:
            rows[(client, project["project_id"])] = {
                "client": client, "project_id": project["project_id"], "sessions": 0, "enqueued": 0,
                "committed": 0, "dead_letter": 0, "dead_letter_recovered": 0, "pending": 0,
                "missing": 0, "wrong_project": 0}
    sessions = []
    if "claude" in clients:
        sessions += claude_sessions(registry, claude_home, since)
    if "codex" in clients:
        sessions += codex_sessions(registry, codex_home, since)

    for client, project_id, session_id in sessions:
        row = rows[(client, project_id)]
        key = capture_session_hash(client, session_id)
        row["sessions"] += 1
        receipt = receipts.get(key)
        stage = receipt.get("stage", "UNKNOWN") if receipt else "NO_RECEIPT"
        if receipt and receipt.get("reason"):
            stage += ":" + str(receipt["reason"])
        bootstrap[f"{client}:{stage}"] += 1
        seen = actions.get(key, set())
        if "ENQUEUED" not in seen and "DUPLICATE" not in seen:
            row["missing"] += 1
            continue
        row["enqueued"] += 1
        if ledger_projects.get(key) not in (None, project_id):
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
                error_codes[f"{client}:{code}"] += 1
        else:
            row["pending"] += 1

    projects = list(rows.values())
    totals: dict[str, int] = defaultdict(int)
    per_client: dict[str, dict[str, int]] = {c: defaultdict(int) for c in clients}
    for row in projects:
        for field in _COUNTS:
            totals[field] += row[field]
            per_client[row["client"]][field] += row[field]
    return {"projects": projects, "totals": dict(totals),
            "clients": {c: dict(v) for c, v in per_client.items()},
            "dead_letter_error_codes": dict(error_codes), "bootstrap_receipts": dict(bootstrap),
            "projects_with_sessions": len({row["project_id"] for row in projects if row["sessions"] > 0})}


def verdict(report: dict[str, Any], *, min_projects: int, min_sessions: int,
            require_clients: tuple[str, ...] = (), min_client_sessions: int = 5) -> str:
    totals = report["totals"]
    if totals.get("missing") or totals.get("dead_letter") or totals.get("wrong_project"):
        return "FAIL"
    if report["projects_with_sessions"] < min_projects or totals.get("sessions", 0) < min_sessions:
        return "INSUFFICIENT_EVIDENCE"
    for client in require_clients:
        if report["clients"].get(client, {}).get("sessions", 0) < min_client_sessions:
            return "INSUFFICIENT_EVIDENCE"
    if totals.get("pending"):
        return "INSUFFICIENT_EVIDENCE"
    return "PASS"


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--vault", default=".")
    parser.add_argument("--claude-home", default=str(Path.home() / ".claude"))
    parser.add_argument("--codex-home", default=str(Path.home() / ".codex"))
    parser.add_argument("--clients", default="claude,codex",
                        help="comma list of clients to audit (claude, codex)")
    parser.add_argument("--require-clients", default="",
                        help="comma list; each must reach --min-client-sessions (step-3 gate: claude,codex)")
    parser.add_argument("--min-client-sessions", type=int, default=5)
    parser.add_argument("--since", help="ISO time; only audit transcripts modified after it")
    parser.add_argument("--min-projects", type=int, default=2)
    parser.add_argument("--min-sessions", type=int, default=20)
    args = parser.parse_args(argv)

    clients = tuple(c for c in args.clients.split(",") if c in {"claude", "codex"})
    required = tuple(c for c in args.require_clients.split(",") if c in {"claude", "codex"})
    report = audit(Path(args.vault), Path(args.claude_home).expanduser(), since=_parse_since(args.since),
                   codex_home=Path(args.codex_home).expanduser(), clients=tuple(dict.fromkeys(clients + required)))
    report["verdict"] = verdict(report, min_projects=args.min_projects, min_sessions=args.min_sessions,
                                require_clients=required, min_client_sessions=args.min_client_sessions)
    report["gate"] = {"min_projects": args.min_projects, "min_sessions": args.min_sessions,
                      "require_clients": list(required), "min_client_sessions": args.min_client_sessions}
    print(json.dumps(report, indent=2, sort_keys=True))
    return {"PASS": 0, "FAIL": 1}.get(report["verdict"], 2)


if __name__ == "__main__":
    raise SystemExit(main())
