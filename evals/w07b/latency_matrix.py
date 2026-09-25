"""W-07B native hook latency matrix (manual, credential-gated; never run by CI).

Implements the "Latency" section of
docs/history/plans/WEAKNESS-W07B-NATIVE-ACCEPTANCE-EVIDENCE-PLAN.md for the
Claude or Codex x {SessionStart, UserPromptSubmit, Stop, SessionEnd}
x {cold, warm}, with five cold and five warm native sessions per client. Reports
p50/p95 in milliseconds, using only the
runtime's own recorded elapsed_ms and status codes (never prompt/transcript
content). Uses the same isolation as evals/w07b/native_smoke.py: a throwaway
vault and client config. Codex authentication is copied into the throwaway
home and never persisted in the report.

Cold/warm is architecturally meaningful only for SessionStart, whose hook
must call ensure_service(wait=True) and may have to boot the background
FastAPI service. Once SessionStart has run in a given process, the
background service is already up for the rest of that same native CLI
invocation, so UserPromptSubmit/Stop/SessionEnd cannot be independently cold
within one process via the public CLI; they are reported warm-only, with
that limitation stated rather than a fabricated cold figure.

Usage: ``python -m evals.w07b.latency_matrix``
"""
from __future__ import annotations

import json
import statistics
import sys
import threading
import time
from pathlib import Path
from tempfile import TemporaryDirectory

from evals.w07b.native_smoke import (
    _client_version, _file_hashes, _invoke as _invoke_native, _live_files, _prepare_client, _repo_head,
)

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

COLD_SAMPLES = 5
WARM_SAMPLES = 5
PROMPT_TEMPLATE = "W07B latency sample {n}: we decided to keep atomic writes for sample {n}."


class _HookPoller:
    """Poll last-hook.json for Stop/SessionEnd elapsed_ms; delivery files
    (read separately) already carry an authoritative per-event elapsed_ms
    for SessionStart/UserPromptSubmit and are not duplicated here."""

    def __init__(self, path: Path):
        self.path = path
        self.samples: list[dict] = []
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        # Seed with whatever is already on disk so a stale entry left over
        # from a *previous* invocation is never recounted as a new sample.
        self._seen_at_start: set[tuple] = set()
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
            self._seen_at_start.add((doc.get("event"), doc.get("at")))
        except (OSError, ValueError):
            pass

    def _run(self):
        seen = set(self._seen_at_start)
        while not self._stop.is_set():
            try:
                doc = json.loads(self.path.read_text(encoding="utf-8"))
                key = (doc.get("event"), doc.get("at"))
                if doc.get("event") in {"Stop", "SessionEnd"} and key not in seen:
                    seen.add(key)
                    self.samples.append(doc)
            except (OSError, ValueError):
                pass
            time.sleep(0.015)

    def __enter__(self):
        self._thread.start()
        return self

    def __exit__(self, *exc):
        time.sleep(0.5)  # trailing grace period for a hook that fires as the process exits
        self._stop.set()
        self._thread.join(timeout=2)


def _identity(prefix: str, *values) -> str:
    from brain_eleven.runtime.storage import identity

    return identity(prefix, *values)


def _stop_service(vault: Path) -> None:
    from brain_eleven.runtime.launcher import request_service
    from brain_eleven.runtime.launcher import _process_alive

    service_file = vault / ".brain-eleven" / "runtime" / "service.json"
    if not service_file.exists():
        return
    launch_file = vault / ".brain-eleven" / "runtime" / "launch.json"
    try:
        launch_pid = json.loads(launch_file.read_text(encoding="utf-8")).get("pid")
    except (OSError, ValueError, TypeError):
        launch_pid = None
    try:
        request_service(vault, "/api/runtime/stop", {})
    except (OSError, ValueError, KeyError):
        pass
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        try:
            request_service(vault, "/api/runtime/status", timeout=0.2)
        except Exception:
            if not _process_alive(launch_pid):
                return
        time.sleep(0.2)
    raise RuntimeError("SERVICE_STOP_TIMEOUT")


def _invoke(vault: Path, settings_path: Path | None, n: int, *, client: str,
            environment: dict[str, str], output_path: Path) -> dict:
    prompt = PROMPT_TEMPLATE.format(n=n)
    last_hook = vault / ".brain-eleven" / "runtime" / "last-hook.json"
    with _HookPoller(last_hook) as poller:
        proc, session_id = _invoke_native(client, vault, settings_path, environment, prompt, output_path)
    result = {"exit_code": proc.returncode, "session_id": session_id, "stop_sessionend": list(poller.samples)}
    deliveries = vault / ".brain-eleven" / "runtime" / "deliveries"
    if session_id:
        bootstrap_key = _identity("delivery_", client, session_id, "bootstrap")
        bootstrap_path = deliveries / (bootstrap_key + ".json")
        if bootstrap_path.exists():
            doc = json.loads(bootstrap_path.read_text(encoding="utf-8"))
            result["session_start"] = {"hook_elapsed_ms": doc.get("hook_elapsed_ms"), "status": doc.get("status")}
        for path in deliveries.glob("*.json") if deliveries.exists() else []:
            if path == bootstrap_path:
                continue
            doc = json.loads(path.read_text(encoding="utf-8"))
            if doc.get("session_hash") == _identity("session_", session_id):
                result["user_prompt_submit"] = {"hook_elapsed_ms": doc.get("hook_elapsed_ms"), "status": doc.get("status")}
    return result


def _percentiles(values: list[float]) -> dict:
    if not values:
        return {"n": 0, "p50": None, "p95": None}
    ordered = sorted(values)
    p50 = statistics.median(ordered)
    p95_index = max(0, -(-95 * len(ordered) // 100) - 1)  # nearest-rank
    return {"n": len(ordered), "p50": round(p50, 1), "p95": round(ordered[p95_index], 1),
            "min": round(ordered[0], 1), "max": round(ordered[-1], 1)}


def run(*, client: str = "claude", cold_samples: int = COLD_SAMPLES,
        warm_samples: int = WARM_SAMPLES) -> dict:
    if cold_samples < 1 or warm_samples < 1:
        raise ValueError("Both sample counts must be positive")
    live_files = _live_files(client)
    live_hashes = _file_hashes(live_files)
    with TemporaryDirectory(prefix="w07b-lat-home-") as home_str, TemporaryDirectory(prefix="w07b-lat-vault-") as vault_str:
        home, vault = Path(home_str), Path(vault_str)
        environment, settings_path = _prepare_client(client, home, vault)

        cells = {"session_start_cold": [], "session_start_warm": [], "user_prompt_submit": [], "stop": [], "session_end": []}
        exit_codes = []
        hook_statuses = {name: [] for name in cells}
        samples = []
        n = 0
        for _ in range(cold_samples):
            n += 1
            _stop_service(vault)
            r = _invoke(vault, settings_path, n, client=client, environment=environment,
                        output_path=home / "last-message.txt")
            exit_codes.append(r["exit_code"])
            samples.append({"phase": "cold", "exit_code": r["exit_code"],
                            "session_id_present": r["session_id"] is not None,
                            "session_start_seen": bool(r.get("session_start")),
                            "user_prompt_submit_seen": bool(r.get("user_prompt_submit")),
                            "stop_seen": any(item.get("event") == "Stop" for item in r["stop_sessionend"]),
                            "session_end_seen": any(item.get("event") == "SessionEnd" for item in r["stop_sessionend"])})
            if r.get("session_start"):
                cells["session_start_cold"].append(r["session_start"]["hook_elapsed_ms"])
                hook_statuses["session_start_cold"].append(r["session_start"]["status"])
            if r.get("user_prompt_submit"):
                cells["user_prompt_submit"].append(r["user_prompt_submit"]["hook_elapsed_ms"])
                hook_statuses["user_prompt_submit"].append(r["user_prompt_submit"]["status"])
            for event_doc in r["stop_sessionend"]:
                key = "stop" if event_doc["event"] == "Stop" else "session_end"
                cells[key].append(event_doc["elapsed_ms"])
                hook_statuses[key].append(event_doc.get("status"))
        for _ in range(warm_samples):
            n += 1
            r = _invoke(vault, settings_path, n, client=client, environment=environment,
                        output_path=home / "last-message.txt")  # service left running
            exit_codes.append(r["exit_code"])
            samples.append({"phase": "warm", "exit_code": r["exit_code"],
                            "session_id_present": r["session_id"] is not None,
                            "session_start_seen": bool(r.get("session_start")),
                            "user_prompt_submit_seen": bool(r.get("user_prompt_submit")),
                            "stop_seen": any(item.get("event") == "Stop" for item in r["stop_sessionend"]),
                            "session_end_seen": any(item.get("event") == "SessionEnd" for item in r["stop_sessionend"])})
            if r.get("session_start"):
                cells["session_start_warm"].append(r["session_start"]["hook_elapsed_ms"])
                hook_statuses["session_start_warm"].append(r["session_start"]["status"])
            if r.get("user_prompt_submit"):
                cells["user_prompt_submit"].append(r["user_prompt_submit"]["hook_elapsed_ms"])
                hook_statuses["user_prompt_submit"].append(r["user_prompt_submit"]["status"])
            for event_doc in r["stop_sessionend"]:
                key = "stop" if event_doc["event"] == "Stop" else "session_end"
                cells[key].append(event_doc["elapsed_ms"])
                hook_statuses[key].append(event_doc.get("status"))

        _stop_service(vault)
        return {"client": client, "client_version": _client_version(client), "repo_head": _repo_head(),
                "live_files_untouched": live_hashes == _file_hashes(live_files),
                "exit_codes": exit_codes,
                "samples": samples,
                "hook_statuses": {name: {status: values.count(status) for status in sorted(set(values), key=str)}
                                  for name, values in hook_statuses.items()},
                "cells": {name: _percentiles(values) for name, values in cells.items()}}


def _gate(report: dict, cold_samples: int, warm_samples: int) -> bool:
    expected = cold_samples + warm_samples
    return (report["live_files_untouched"] and all(code == 0 for code in report["exit_codes"]) and
            report["cells"]["session_start_cold"]["n"] >= cold_samples and
            report["cells"]["session_start_warm"]["n"] >= warm_samples and
            all(report["cells"][name]["n"] >= expected for name in ("user_prompt_submit", "stop", "session_end")) and
            all(cell["p95"] is not None and cell["p95"] < 3000 for cell in report["cells"].values()))


def main(argv=None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--client", choices=("claude", "codex"), default="claude")
    parser.add_argument("--cold-samples", type=int, default=COLD_SAMPLES)
    parser.add_argument("--warm-samples", type=int, default=WARM_SAMPLES)
    parser.add_argument("--report", type=Path, default=None)
    args = parser.parse_args(argv)
    report = run(client=args.client, cold_samples=args.cold_samples, warm_samples=args.warm_samples)
    report["gate_passed"] = _gate(report, args.cold_samples, args.warm_samples)
    print(json.dumps(report, indent=2))
    if args.report:
        args.report.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return 0 if report["gate_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
