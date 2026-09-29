"""Credential-gated native W-07B hook latency matrix; never run by CI.

Runs the real Claude and Codex executables against a temporary vault and
isolated client settings.  It measures SessionStart, UserPromptSubmit, Stop,
and SessionEnd in cold and warm service states, with five samples per cell.
For a cold non-SessionStart event, the harness stops the service after the
preceding hook has durably recorded its receipt.  Codex hooks are validated
against the already installed temporary profile; this module never rewrites
the Codex hooks file after it has been reviewed.

Only event names, elapsed milliseconds, bounded status codes, sample counts,
the implementation revision, and harness hash are reported.  Prompts,
transcripts, session identifiers, profile locations, and exceptions are never
written to the report.

Usage: ``python -m evals.w07b.latency_matrix --vault <temporary-vault>``
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import statistics
import subprocess
import sys
import threading
import time
from collections import Counter
from pathlib import Path
from tempfile import TemporaryDirectory

from .client_process import run_claude

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

CLIENTS = ("claude", "codex")
EVENTS = ("SessionStart", "UserPromptSubmit", "Stop", "SessionEnd")
PHASES = ("cold", "warm")
SAMPLE_COUNT = 5
CLIENT_TIMEOUT_SECONDS = 120
POLL_SECONDS = 0.005
_SAFE_STATUS = re.compile(r"^[A-Z0-9_]{1,64}$")
_PREDECESSOR = {
    "SessionStart": None,
    "UserPromptSubmit": "SessionStart",
    "Stop": "UserPromptSubmit",
    "SessionEnd": "Stop",
}


def _cell_key(client: str, event: str, phase: str) -> str:
    return f"{client}:{event}:{phase}"


def _read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def _safe_status(value, fallback: str = "UNKNOWN") -> str:
    return value if isinstance(value, str) and _SAFE_STATUS.fullmatch(value) else fallback


def _percentiles(values: list[int | float]) -> dict:
    ordered = sorted(value for value in values if isinstance(value, (int, float))
                     and not isinstance(value, bool) and value >= 0)
    if not ordered:
        return {"n": 0, "p50_ms": None, "p95_ms": None}
    p95_index = max(0, -(-95 * len(ordered) // 100) - 1)  # nearest-rank
    return {
        "n": len(ordered),
        "p50_ms": round(statistics.median(ordered), 1),
        "p95_ms": round(ordered[p95_index], 1),
        "min_ms": round(ordered[0], 1),
        "max_ms": round(ordered[-1], 1),
    }


def _budget_ms(event: str) -> int:
    # These are existing runtime contracts: SessionStart's 2.5s hook budget
    # and the 3s native hook timeout installed for every event.
    return 2500 if event == "SessionStart" else 3000


def _summarize_cell(client: str, event: str, phase: str,
                    attempts: list[dict], expected_samples: int) -> dict:
    durations = [item["elapsed_ms"] for item in attempts
                 if isinstance(item.get("elapsed_ms"), (int, float))
                 and not isinstance(item.get("elapsed_ms"), bool)]
    percentiles = _percentiles(durations)
    statuses = Counter(_safe_status(item.get("status_code")) for item in attempts)
    client_statuses = Counter(_safe_status(item.get("client_status")) for item in attempts)
    p95 = percentiles["p95_ms"]
    return {
        "client": client,
        "event": event,
        "phase": phase,
        "attempts": len(attempts),
        "expected_samples": expected_samples,
        **percentiles,
        "status_counts": dict(sorted(statuses.items())),
        "client_status_counts": dict(sorted(client_statuses.items())),
        "budget_ms": _budget_ms(event),
        "within_budget": p95 is not None and p95 <= _budget_ms(event),
    }


def _summarize_matrix(observations: dict, expected_samples: int = SAMPLE_COUNT) -> dict:
    cells = [
        _summarize_cell(client, event, phase,
                        observations.get(_cell_key(client, event, phase), []),
                        expected_samples)
        for client in CLIENTS
        for event in EVENTS
        for phase in PHASES
    ]
    complete = all(cell["n"] >= expected_samples for cell in cells)
    within_budget = all(cell["within_budget"] for cell in cells)
    clients_completed = all(
        cell["client_status_counts"].get("OK", 0) >= expected_samples
        for cell in cells
    )
    return {
        "schema": 1,
        "sample_count_per_cell": expected_samples,
        "cell_count": len(cells),
        "complete": complete,
        "within_budget": within_budget,
        "native_runs_completed": clients_completed,
        "acceptance": complete and within_budget and clients_completed,
        "cells": cells,
    }


def _identity(prefix: str, *values) -> str:
    from brain_eleven.runtime.storage import identity

    return identity(prefix, *values)


def _stop_service(vault: Path) -> bool:
    from brain_eleven.runtime.launcher import request_service

    service_file = vault / ".brain-eleven" / "runtime" / "service.json"
    if not service_file.exists():
        return True
    try:
        request_service(vault, "/api/runtime/stop", {}, timeout=0.5)
    except Exception:
        pass
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        try:
            request_service(vault, "/api/runtime/status", timeout=0.2)
            time.sleep(0.05)
        except Exception:
            return True
    return False


def _ensure_service(vault: Path) -> bool:
    from brain_eleven.runtime.launcher import ensure_service

    return ensure_service(vault, wait=True, wait_timeout=8)


class _HookPoller:
    """Observe only durable delivery timing and content-free terminal timing."""

    def __init__(self, vault: Path, client: str, stop_after: str | None = None):
        self.vault = vault
        self.client = client
        self.stop_after = stop_after
        root = vault / ".brain-eleven" / "runtime"
        self.deliveries = root / "deliveries"
        self.last_hook = root / "last-hook.json"
        self.samples: dict[str, dict] = {}
        self.stop_results: dict[str, bool] = {}
        self._seen_deliveries = {path.name for path in self.deliveries.glob("*.json")} \
            if self.deliveries.exists() else set()
        previous = _read_json(self.last_hook)
        self._last_key = (previous.get("event"), previous.get("at"))
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def _record(self, event: str, status_code: str, elapsed_ms, *, stage=None):
        if event not in EVENTS:
            return
        sample = {
            "status_code": _safe_status(status_code),
            "elapsed_ms": elapsed_ms if isinstance(elapsed_ms, (int, float))
                and not isinstance(elapsed_ms, bool) and elapsed_ms >= 0 else None,
        }
        if isinstance(stage, str):
            sample["stage"] = _safe_status(stage)
        with self._lock:
            if event in self.samples:
                return
            self.samples[event] = sample
        # Stop only after the preceding hook has durably written its receipt;
        # the native CLI will invoke the requested cold hook next.
        if event == self.stop_after:
            self.stop_results[event] = _stop_service(self.vault)

    def _scan_deliveries(self):
        if not self.deliveries.exists():
            return
        for path in self.deliveries.glob("*.json"):
            if path.name in self._seen_deliveries:
                continue
            self._seen_deliveries.add(path.name)
            doc = _read_json(path)
            event = doc.get("event")
            if doc.get("client") != self.client or event not in {"SessionStart", "UserPromptSubmit"}:
                continue
            stage = doc.get("stage")
            code = stage if isinstance(stage, str) else doc.get("status")
            self._record(event, _safe_status(code), doc.get("hook_elapsed_ms"), stage=stage)

    def _scan_last_hook(self):
        doc = _read_json(self.last_hook)
        key = (doc.get("event"), doc.get("at"))
        event = doc.get("event")
        if event in {"Stop", "SessionEnd"} and key != self._last_key:
            self._last_key = key
            if doc.get("client") == self.client:
                self._record(event, _safe_status(doc.get("status")), doc.get("elapsed_ms"))
        elif key != self._last_key:
            self._last_key = key

    def _run(self):
        while not self._stop.is_set():
            self._scan_deliveries()
            self._scan_last_hook()
            time.sleep(POLL_SECONDS)

    def __enter__(self):
        self._thread.start()
        return self

    def __exit__(self, *exc):
        time.sleep(0.5)  # allow the final event receipt to become durable
        self._stop.set()
        self._thread.join(timeout=8)


def _validate_codex_binding(vault: Path, home: Path) -> None:
    """Require the reviewed, isolated hooks file to target this exact vault."""
    from brain_eleven.runtime.install import client_paths, hook_command

    config_path = (home / "hooks.json").resolve()
    try:
        if client_paths(home.parent)["codex"].resolve() != config_path:
            raise RuntimeError("CODEX_HOOK_CONFIG_MISMATCH")
    except (OSError, ValueError, KeyError):
        raise RuntimeError("CODEX_HOOK_CONFIG_MISMATCH") from None

    manifest = _read_json(vault / ".brain-eleven" / "runtime" / "installation.json")
    record = manifest.get("clients", {}).get("codex", {})
    try:
        if Path(record.get("path", "")).resolve() != config_path:
            raise RuntimeError("CODEX_HOOK_CONFIG_MISMATCH")
    except (OSError, TypeError, ValueError):
        raise RuntimeError("CODEX_HOOK_CONFIG_MISMATCH") from None

    installed = record.get("entries")
    current = _read_json(config_path).get("hooks")
    if not isinstance(installed, dict) or not isinstance(current, dict):
        raise RuntimeError("CODEX_HOOK_CONFIG_MISMATCH")
    for event in EVENTS:
        event_record = installed.get(event)
        owned = event_record.get("hooks") if isinstance(event_record, dict) else None
        active = current.get(event)
        expected = hook_command(vault, "codex", event)
        if (not isinstance(owned, list) or not isinstance(active, list)
                or not any(isinstance(item, dict) and item.get("command") == expected for item in owned)
                or not any(item in active for item in owned)):
            raise RuntimeError("CODEX_HOOK_BINDING_MISMATCH")


def _run_native(client: str, vault: Path, settings_path: Path | None,
                codex_env: dict[str, str] | None, sample_number: int) -> str:
    prompt = f"W07B native latency sample {sample_number}: reply briefly with OK; do not use tools or run commands."
    try:
        if client == "claude":
            proc = run_claude(vault, settings_path, prompt, timeout=CLIENT_TIMEOUT_SECONDS)
        else:
            proc = subprocess.run(
                ["codex", "exec", "--json", "--sandbox", "read-only", "--cd", str(vault), prompt],
                cwd=str(vault), capture_output=True, text=True, encoding="utf-8",
                timeout=CLIENT_TIMEOUT_SECONDS, env=codex_env,
            )
    except subprocess.TimeoutExpired:
        return "TIMEOUT"
    except FileNotFoundError:
        return "CLIENT_UNAVAILABLE"
    except OSError:
        return "CLIENT_ERROR"
    return "OK" if proc.returncode == 0 else "CLIENT_EXIT"


def _client_version(client: str, codex_env: dict[str, str] | None = None) -> str:
    try:
        proc = subprocess.run([client, "--version"], capture_output=True, text=True,
                              encoding="utf-8", timeout=15, env=codex_env)
    except (OSError, subprocess.TimeoutExpired):
        return "unavailable"
    value = (proc.stdout or proc.stderr or "").strip()
    # Version output is content-free; reject anything unexpected rather than
    # leaking a path or arbitrary executable output to the report.
    return value[:64] if re.fullmatch(r"[A-Za-z0-9 ._+\-]{1,64}", value) else "unknown"


def _repo_head() -> str:
    try:
        proc = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO,
                              capture_output=True, text=True, timeout=15)
    except (OSError, subprocess.TimeoutExpired):
        return "unknown"
    value = proc.stdout.strip()
    return value if re.fullmatch(r"[0-9a-f]{40,64}", value) else "unknown"


def run(vault: Path, samples: int = SAMPLE_COUNT) -> dict:
    from brain_eleven.runtime.install import install
    from .codex_native_smoke import _codex_environment, _codex_home

    if samples < SAMPLE_COUNT:
        raise ValueError("SAMPLE_COUNT_BELOW_PLAN")
    vault = Path(vault).resolve()
    temp_root = Path(__import__("tempfile").gettempdir()).resolve()
    try:
        if os.path.normcase(os.path.commonpath((str(vault), str(temp_root)))) != os.path.normcase(str(temp_root)):
            raise RuntimeError("VAULT_NOT_ISOLATED")
    except ValueError:
        raise RuntimeError("VAULT_NOT_ISOLATED") from None

    codex_home = _codex_home()
    try:
        if os.path.normcase(os.path.commonpath((str(vault), str(codex_home.parent)))) != os.path.normcase(str(codex_home.parent)):
            raise RuntimeError("VAULT_NOT_BOUND_TO_CODEX_HOME")
    except ValueError:
        raise RuntimeError("VAULT_NOT_BOUND_TO_CODEX_HOME") from None
    _validate_codex_binding(vault, codex_home)
    codex_env = _codex_environment(codex_home)

    observations = {
        _cell_key(client, event, phase): []
        for client in CLIENTS for event in EVENTS for phase in PHASES
    }
    versions = {"codex": _client_version("codex", codex_env)}
    versions["claude"] = _client_version("claude")
    sample_number = 0

    with TemporaryDirectory(prefix="w07b-lat-claude-hooks-") as claude_home_str:
        claude_home = Path(claude_home_str)
        # Install only Claude hooks into temporary settings. The Codex config
        # was validated above and is never written by this run.
        install(str(vault), home=str(claude_home), clients=("claude",))
        claude_settings = claude_home / ".claude" / "settings.json"

        try:
            for client in CLIENTS:
                for event in EVENTS:
                    for phase in PHASES:
                        predecessor = _PREDECESSOR[event]
                        for _ in range(samples):
                            sample_number += 1
                            if phase == "cold":
                                initial_ready = _stop_service(vault)
                                stop_after = predecessor
                            else:
                                initial_ready = _ensure_service(vault)
                                stop_after = None

                            with _HookPoller(vault, client, stop_after=stop_after) as poller:
                                client_status = _run_native(
                                    client, vault,
                                    claude_settings if client == "claude" else None,
                                    codex_env if client == "codex" else None,
                                    sample_number,
                                )

                            observation = poller.samples.get(event)
                            cold_ready = (event == "SessionStart" or predecessor is None
                                          or poller.stop_results.get(predecessor) is True)
                            if not initial_ready:
                                status_code = "SERVICE_STATE_UNVERIFIED"
                                elapsed_ms = None
                            elif phase == "cold" and not cold_ready:
                                status_code = "COLD_STATE_UNVERIFIED"
                                elapsed_ms = None
                            elif observation is None:
                                status_code = "EVENT_NOT_OBSERVED"
                                elapsed_ms = None
                            else:
                                status_code = observation["status_code"]
                                elapsed_ms = observation["elapsed_ms"]
                            observations[_cell_key(client, event, phase)].append({
                                "status_code": status_code,
                                "elapsed_ms": elapsed_ms,
                                "client_status": client_status,
                            })
        finally:
            _stop_service(vault)

    report = _summarize_matrix(observations, expected_samples=samples)
    report["client_versions"] = versions
    report["implementation_head"] = _repo_head()
    report["harness_sha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    return report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vault", type=Path, required=True)
    parser.add_argument("--samples", type=int, default=SAMPLE_COUNT)
    args = parser.parse_args(argv)
    try:
        report = run(args.vault, samples=args.samples)
    except (OSError, RuntimeError, ValueError) as exc:
        code = str(exc) if _SAFE_STATUS.fullmatch(str(exc)) else "HARNESS_ERROR"
        print(json.dumps({"acceptance": False, "failure_code": code}, indent=2))
        return 1
    print(json.dumps(report, indent=2))
    return 0 if report["acceptance"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
