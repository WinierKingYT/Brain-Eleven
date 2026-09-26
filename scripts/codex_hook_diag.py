#!/usr/bin/env python3
"""Read-only: why did a Codex Stop hook not reach the capture ledger?

For each Codex rollout modified since --since, prints whether its cwd would
pass the runtime's capture scope check (the same ``allowed`` the hook uses)
and whether any of its session ids appears in the capture ledger. Prints
fixed codes and booleans only; the cwd is shown so the owner can compare it
with the registered project root on their own machine.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from brain_eleven.runtime.storage import RuntimeConfig  # noqa: E402
from brain_eleven.runtime.worker import allowed, capture_session_hash  # noqa: E402
from capture_gap_audit import _codex_meta, _parse_since, _recent, load_ledger, load_registry  # noqa: E402


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--vault", default=".")
    parser.add_argument("--codex-home", default=str(Path.home() / ".codex"))
    parser.add_argument("--since")
    args = parser.parse_args(argv)
    vault = Path(args.vault)
    since = _parse_since(args.since)
    config = RuntimeConfig(vault).load()
    ledger = {}
    for record in load_ledger(vault):
        ledger.setdefault(record.get("session_id_hash"), set()).add(str(record.get("action")))
    rollouts = []
    for rollout in sorted((Path(args.codex_home).expanduser() / "sessions").rglob("*.jsonl")):
        if not _recent(rollout, since):
            continue
        meta = _codex_meta(rollout)
        if not meta:
            rollouts.append({"file": rollout.name, "session_meta": "MISSING_OR_UNREADABLE"})
            continue
        ids, cwd = meta
        record = allowed(vault, cwd)
        seen = sorted(set().union(*(ledger.get(capture_session_hash("codex", i), set()) for i in ids)))
        rollouts.append({"file": rollout.name, "cwd": cwd, "capture_allowed": bool(record),
                         "project_id": record["project_id"] if record else None,
                         "ledger_actions": seen})
    last = RuntimeConfig(vault).root / "last-capture-codex.json"
    report = {
        "mode": config.get("mode"),
        "capture_project_ids": config.get("project_ids"),
        "registered_roots": [p["root"] for p in load_registry(vault)],
        "codex_rollouts": rollouts,
        "last_capture_codex": json.loads(last.read_text(encoding="utf-8")) if last.is_file() else None,
    }
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
