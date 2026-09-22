"""W-07B Claude native hook latency matrix (manual, credential-gated; never run by CI).

Implements the "Latency" section of
docs/history/plans/WEAKNESS-W07B-NATIVE-ACCEPTANCE-EVIDENCE-PLAN.md for the
Claude side only: Claude x {SessionStart, UserPromptSubmit, Stop, SessionEnd}
x {cold, warm}, >=5 samples per cell, p50/p95 in milliseconds, using only the
runtime's own recorded elapsed_ms and status codes (never prompt/transcript
content). Uses the same isolation as evals/w07b/native_smoke.py: a throwaway
vault and throwaway client config; the live vault and live
~/.claude/settings.json are never read or written.

Cold/warm is architecturally meaningful only for SessionStart, whose hook
must call ensure_service(wait=True) and may have to boot the background
FastAPI service. Once SessionStart has run in a given process, the
background service is already up for the rest of that same `claude -p`
invocation, so UserPromptSubmit/Stop/SessionEnd cannot be independently cold
within one process via the public CLI; they are reported warm-only, with
that limitation stated rather than a fabricated cold figure.

Usage: ``python -m evals.w07b.latency_matrix``
"""
from __future__ import annotations

import json
import statistics
import subprocess
import sys
import threading
import time
from pathlib import Path
from tempfile import TemporaryDirectory

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

    service_file = vault / ".brain-eleven" / "runtime" / "service.json"
    if not service_file.exists():
        return
    try:
        request_service(vault, "/api/runtime/stop", {})
    except (OSError, ValueError, KeyError):
        pass
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        try:
            request_service(vault, "/api/runtime/status", timeout=0.2)
            time.sleep(0.2)
        except Exception:
            return


def _invoke(vault: Path, settings_path: Path, n: int) -> dict:
    prompt = PROMPT_TEMPLATE.format(n=n)
    cmd = ["claude", "-p", prompt, "--settings", str(settings_path), "--setting-sources", "",
           "--strict-mcp-config", "--tools", "", "--output-format", "json"]
    last_hook = vault / ".brain-eleven" / "runtime" / "last-hook.json"
    with _HookPoller(last_hook) as poller:
        proc = subprocess.run(cmd, cwd=str(vault), capture_output=True, text=True, encoding="utf-8", timeout=120)
    session_id = None
    try:
        session_id = json.loads(proc.stdout).get("session_id")
    except (ValueError, TypeError):
        pass
    result = {"exit_code": proc.returncode, "session_id": session_id, "stop_sessionend": list(poller.samples)}
    deliveries = vault / ".brain-eleven" / "runtime" / "deliveries"
    if session_id:
        bootstrap_key = _identity("delivery_", "claude", session_id, "bootstrap")
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


def run() -> dict:
    from brain_eleven.runtime.install import install

    with TemporaryDirectory(prefix="w07b-lat-home-") as home_str, TemporaryDirectory(prefix="w07b-lat-vault-") as vault_str:
        home, vault = Path(home_str), Path(vault_str)
        install(str(vault), home=str(home), clients=("claude",))
        settings_path = home / "isolated_hooks.json"
        settings_path.write_text(json.dumps({"hooks": json.loads((home / ".claude" / "settings.json").read_text(encoding="utf-8"))["hooks"]}), encoding="utf-8")

        cells = {"session_start_cold": [], "session_start_warm": [], "user_prompt_submit": [], "stop": [], "session_end": []}
        n = 0
        for _ in range(COLD_SAMPLES):
            n += 1
            _stop_service(vault)
            r = _invoke(vault, settings_path, n)
            if r.get("session_start"):
                cells["session_start_cold"].append(r["session_start"]["hook_elapsed_ms"])
            if r.get("user_prompt_submit"):
                cells["user_prompt_submit"].append(r["user_prompt_submit"]["hook_elapsed_ms"])
            for event_doc in r["stop_sessionend"]:
                key = "stop" if event_doc["event"] == "Stop" else "session_end"
                cells[key].append(event_doc["elapsed_ms"])
        for _ in range(WARM_SAMPLES):
            n += 1
            r = _invoke(vault, settings_path, n)  # service left running from the previous sample
            if r.get("session_start"):
                cells["session_start_warm"].append(r["session_start"]["hook_elapsed_ms"])
            if r.get("user_prompt_submit"):
                cells["user_prompt_submit"].append(r["user_prompt_submit"]["hook_elapsed_ms"])
            for event_doc in r["stop_sessionend"]:
                key = "stop" if event_doc["event"] == "Stop" else "session_end"
                cells[key].append(event_doc["elapsed_ms"])

        return {name: _percentiles(values) for name, values in cells.items()}


def main(argv=None) -> int:
    report = run()
    print(json.dumps(report, indent=2))
    ok = report["session_start_cold"]["n"] >= COLD_SAMPLES and report["session_start_warm"]["n"] >= WARM_SAMPLES
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
