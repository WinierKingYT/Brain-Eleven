"""W-07B isolated native Claude smoke (manual, credential-gated; never run by CI).

Implements the "Isolated native smoke" section of
docs/history/plans/WEAKNESS-W07B-NATIVE-ACCEPTANCE-EVIDENCE-PLAN.md for the
Claude side only: build a throwaway vault and a throwaway client config,
invoke the real ``claude`` executable against them with the live global
settings and this repository's project-local settings excluded, then verify
the hook -> queue -> terminal receipt -> review/canonical effect chain by
opaque ID, never a bare ``COMPLETED`` queue row.

Requires a real, already-authenticated ``claude`` CLI on PATH. It never reads
or writes the live vault, the live global ``~/.claude/settings.json`` or this
repository's own runtime state; every artifact lives under a
``tempfile.TemporaryDirectory`` that is removed even on failure.

Usage: ``python -m evals.w07b.native_smoke [--repetitions N]``. For a
reusable isolated login, set ``W07B_CLAUDE_CONFIG_DIR`` to a disposable
directory under system temp.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from tempfile import TemporaryDirectory

from .client_process import run_claude

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

# Synthetic, content-free prompts: no real user data, deterministic shape
# (a stated decision), one distinct fact per repetition so dedup cannot mask
# a missed run.
PROMPTS = [
    "W07B isolated smoke rep {n}: we decided to use SQLite for claude-smoke-key-{n}.",
    "W07B isolated smoke rep {n}: we decided to prefer atomic rename for claude-smoke-key-{n}.",
    "W07B isolated smoke rep {n}: we decided to keep the vault manifest for claude-smoke-key-{n}.",
]


@dataclass
class RunResult:
    repetition: int
    exit_code: int
    elapsed_s: float
    session_hash: str | None
    ledger_terminal: dict
    hook_receipts: dict
    queue_terminal_state: str | None
    capture_receipt_status: str | None
    review_effect_id: str | None
    memory_revision_before: int
    memory_revision_after: int
    failure_code: str | None


@dataclass
class Report:
    client_version: str
    repo_head: str
    live_settings_hash_before: str | None
    live_settings_hash_after: str | None
    runs: list = field(default_factory=list)


def _client_version() -> str:
    proc = subprocess.run(["claude", "--version"], capture_output=True, text=True, timeout=15)
    value = (proc.stdout or proc.stderr or "").strip()
    return value[:64] if re.fullmatch(r"[A-Za-z0-9 ._+\-]{1,64}", value) else "unknown"


def _repo_head() -> str:
    proc = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO, capture_output=True, text=True, timeout=15)
    value = proc.stdout.strip()
    return value if re.fullmatch(r"[0-9a-f]{40,64}", value) else "unknown"


def _sha256(path: Path) -> str | None:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None


def _memory_revision(vault: Path) -> int:
    path = vault / ".claude" / "validated-memory.json"
    if not path.exists():
        return -1
    return json.loads(path.read_text(encoding="utf-8"))["revision"]


def _ledger_terminal_counts(vault: Path) -> dict:
    path = vault / ".brain-eleven" / "capture" / "capture-ledger.jsonl"
    if not path.exists():
        return {}
    from collections import Counter

    actions = Counter(json.loads(line)["action"] for line in path.read_text(encoding="utf-8").splitlines() if line.strip())
    return dict(actions)


def run(repetitions: int) -> Report:
    from brain_eleven.runtime.install import install
    from brain_eleven.runtime.worker import capture_session_hash
    from .codex_native_smoke import (
        _capture_receipt,
        _last_capture,
        _session_receipts,
        _verified_review_id,
        _wait_for_capture,
    )
    from .latency_matrix import _stop_service

    live_settings = Path.home() / ".claude" / "settings.json"
    before_hash = _sha256(live_settings)
    report = Report(client_version=_client_version(), repo_head=_repo_head(),
                     live_settings_hash_before=before_hash, live_settings_hash_after=None)

    with TemporaryDirectory(prefix="w07b-home-") as home_str, TemporaryDirectory(prefix="w07b-vault-") as vault_str:
        home, vault = Path(home_str), Path(vault_str)
        install(str(vault), home=str(home), clients=("claude",))
        settings_path = home / ".claude" / "settings.json"
        isolated = {"hooks": json.loads(settings_path.read_text(encoding="utf-8"))["hooks"]}
        isolated_path = home / "isolated_hooks.json"
        isolated_path.write_text(json.dumps(isolated), encoding="utf-8")

        try:
            for n in range(1, repetitions + 1):
                prompt = PROMPTS[(n - 1) % len(PROMPTS)].format(n=n)
                marker = f"claude-smoke-key-{n}"
                before_revision = _memory_revision(vault)
                started = time.monotonic()
                try:
                    proc = run_claude(vault, isolated_path, prompt, timeout=120)
                    exit_code = proc.returncode
                    client_status = "OK" if exit_code == 0 else "CLIENT_EXIT"
                except subprocess.TimeoutExpired:
                    proc = None
                    exit_code = 124
                    client_status = "TIMEOUT"
                elapsed = time.monotonic() - started
                session_id = None
                if proc is not None:
                    try:
                        session_id = json.loads(proc.stdout).get("session_id")
                    except (ValueError, TypeError):
                        pass
                job = _wait_for_capture(vault, session_id, "claude") if session_id else {}
                receipts = _session_receipts(vault, session_id, "claude") if session_id else {}
                capture = _last_capture(vault, session_id, "claude") if session_id else {}
                effect_receipt = _capture_receipt(vault, job) if job else {}
                review_id = _verified_review_id(
                    vault, session_id, marker, effect_receipt.get("review_effect_ids", []), "claude"
                ) if session_id else None
                revision_after = _memory_revision(vault)
                checks = {
                    "session_start_receipt_observed": "SessionStart" in receipts,
                    "user_prompt_submit_receipt_observed": "UserPromptSubmit" in receipts,
                    "queue_committed": job.get("status") == "COMMITTED",
                    "capture_receipt_verified": effect_receipt.get("status") == "EFFECT_VERIFIED",
                    "review_effect_verified": review_id is not None,
                    "memory_revision_unchanged": before_revision == revision_after,
                }
                failure_code = None
                if client_status != "OK":
                    failure_code = client_status
                else:
                    for check, passed in checks.items():
                        if not passed:
                            failure_code = {
                                "session_start_receipt_observed": "SESSIONSTART_RECEIPT_MISSING",
                                "user_prompt_submit_receipt_observed": "USERPROMPT_RECEIPT_MISSING",
                                "queue_committed": capture.get("error_code") or "CAPTURE_NOT_TERMINAL",
                                "capture_receipt_verified": "CAPTURE_RECEIPT_NOT_VERIFIED",
                                "review_effect_verified": "EXPECTED_REVIEW_EFFECT_MISSING",
                                "memory_revision_unchanged": "CANONICAL_REVISION_CHANGED",
                            }[check]
                            break
                report.runs.append(RunResult(
                    repetition=n,
                    exit_code=exit_code,
                    elapsed_s=round(elapsed, 3),
                    session_hash=capture_session_hash("claude", session_id) if session_id else None,
                    ledger_terminal=_ledger_terminal_counts(vault),
                    hook_receipts=receipts,
                    queue_terminal_state=job.get("status"),
                    capture_receipt_status=effect_receipt.get("status"),
                    review_effect_id=review_id,
                    memory_revision_before=before_revision,
                    memory_revision_after=revision_after,
                    failure_code=failure_code,
                ))
        finally:
            _stop_service(vault)
        report.live_settings_hash_after = _sha256(live_settings)
    return report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repetitions", type=int, default=2)
    parser.add_argument("--report", type=Path, default=None, help="optional path to write the JSON report")
    args = parser.parse_args(argv)

    try:
        report = run(args.repetitions)
    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as exc:
        code = str(exc) if re.fullmatch(r"[A-Z0-9_]{1,64}", str(exc)) else "HARNESS_ERROR"
        print(json.dumps({"trust_verdict": "BOUNDED_UNVERIFIED_CLAUDE", "failure_code": code}, indent=2))
        return 1
    live_untouched = report.live_settings_hash_before == report.live_settings_hash_after
    verified = bool(report.runs) and all(
        r.exit_code == 0 and r.failure_code is None for r in report.runs
    )
    payload = {
        "client_version": report.client_version,
        "repo_head": report.repo_head,
        "trust_verdict": "VERIFIED" if verified else "BOUNDED_UNVERIFIED_CLAUDE",
        "live_global_settings_untouched": live_untouched,
        "runs": [
            {"repetition": r.repetition, "exit_code": r.exit_code, "elapsed_s": r.elapsed_s,
             "session_hash": r.session_hash, "hook_receipts": r.hook_receipts,
             "ledger_terminal_counts": r.ledger_terminal,
             "queue_terminal_state": r.queue_terminal_state,
             "capture_receipt_status": r.capture_receipt_status,
             "review_effect_id": r.review_effect_id,
             "memory_revision_unchanged": r.memory_revision_before == r.memory_revision_after,
             "failure_code": r.failure_code}
            for r in report.runs
        ],
    }
    print(json.dumps(payload, indent=2))
    if args.report:
        args.report.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    if not live_untouched:
        print("FATAL: live global settings.json hash changed", file=sys.stderr)
        return 2
    ok = verified
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
