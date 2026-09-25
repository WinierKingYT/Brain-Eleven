"""W-07B isolated native client smoke (manual, credential-gated; never run by CI).

Implements the "Isolated native smoke" section of
docs/history/plans/WEAKNESS-W07B-NATIVE-ACCEPTANCE-EVIDENCE-PLAN.md for the
Build a throwaway vault and client config, invoke the real ``claude`` or
``codex`` executable, then verify
the hook -> queue -> terminal receipt -> review/canonical effect chain by
opaque ID, never a bare ``COMPLETED`` queue row.

Requires the selected real, already-authenticated CLI on PATH. Codex auth is
copied byte-for-byte into the throwaway ``CODEX_HOME`` and removed with it;
the harness never parses or reports credential contents. It never writes the
live vault or live client configuration; every artifact lives under a
``tempfile.TemporaryDirectory`` that is removed even on failure.

Usage: ``python -m evals.w07b.native_smoke --client codex [--repetitions N]``
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from tempfile import TemporaryDirectory

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

# Synthetic, content-free prompts: no real user data, deterministic shape
# (a stated decision), one distinct fact per repetition so dedup cannot mask
# a missed run.
PROMPTS = [
    "W07B isolated smoke rep {n}: we decided to use SQLite for isolated capture test {n}.",
    "W07B isolated smoke rep {n}: we decided to prefer atomic rename for isolated capture test {n}.",
    "W07B isolated smoke rep {n}: we decided to keep the vault manifest for isolated capture test {n}.",
]


class RetryingTemporaryDirectory(TemporaryDirectory):
    """Allow a stopped Windows service's final file write to finish."""

    def cleanup(self):
        for attempt in range(50):
            try:
                return super().cleanup()
            except OSError as exc:
                if getattr(exc, "winerror", None) not in {32, 145} or attempt == 49:
                    raise
                time.sleep(0.2)


@dataclass
class RunResult:
    repetition: int
    exit_code: int
    elapsed_s: float
    session_id: str | None
    ledger_terminal: dict
    review_ids: list
    new_review_count: int
    verified_terminal_count: int
    dead_letter_count: int
    memory_revision_before: int
    memory_revision_after: int


@dataclass
class Report:
    client: str
    client_version: str
    repo_head: str
    live_settings_hash_before: str | None
    live_settings_hash_after: str | None
    runs: list = field(default_factory=list)


def _client_version(client: str) -> str:
    proc = subprocess.run([client, "--version"], capture_output=True, text=True, timeout=15)
    return proc.stdout.strip() or proc.stderr.strip()


def _repo_head() -> str:
    proc = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO, capture_output=True, text=True, timeout=15)
    return proc.stdout.strip()


def _sha256(path: Path) -> str | None:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None


def _memory_revision(vault: Path) -> int:
    path = vault / ".claude" / "validated-memory.json"
    if not path.exists():
        return -1
    return json.loads(path.read_text(encoding="utf-8"))["revision"]


def _stop_service(vault: Path) -> None:
    from brain_eleven.runtime.launcher import request_service

    try:
        request_service(vault, "/api/runtime/stop", {})
    except (OSError, ValueError, KeyError):
        return
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        try:
            request_service(vault, "/api/runtime/status", timeout=0.2)
            time.sleep(0.2)
        except Exception:
            return


def _codex_live_files() -> list[Path]:
    root = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex")))
    return [root / "auth.json", root / "hooks.json"]


def _live_files(client: str) -> list[Path]:
    if client == "claude":
        return [Path.home() / ".claude" / "settings.json"]
    return _codex_live_files()


def _file_hashes(paths: list[Path]) -> list[str | None]:
    return [_sha256(path) for path in paths]


def _prepare_client(client: str, home: Path, vault: Path) -> tuple[dict[str, str], Path | None]:
    from brain_eleven.runtime.install import install

    install(str(vault), home=str(home), clients=(client,))
    environment = os.environ.copy()
    if client == "claude":
        installed = home / ".claude" / "settings.json"
        isolated = {"hooks": json.loads(installed.read_text(encoding="utf-8"))["hooks"]}
        settings = home / "isolated_hooks.json"
        settings.write_text(json.dumps(isolated), encoding="utf-8")
        return environment, settings

    live_auth = _codex_live_files()[0]
    if not live_auth.is_file():
        raise RuntimeError("BOUNDED_UNVERIFIED_CODEX_AUTH_MISSING")
    codex_home = home / ".codex"
    shutil.copy2(live_auth, codex_home / "auth.json")
    environment["CODEX_HOME"] = str(codex_home)
    return environment, None


def _invoke(client: str, vault: Path, settings: Path | None, environment: dict[str, str], prompt: str,
            output_path: Path, *, resume_session: str | None = None) -> tuple[subprocess.CompletedProcess[str], str | None]:
    if client == "claude":
        command = ["claude", "-p", prompt, "--settings", str(settings), "--setting-sources", "",
                   "--strict-mcp-config", "--tools", "", "--output-format", "json"]
        if resume_session:
            command += ["--resume", resume_session]
        proc = subprocess.run(command, cwd=str(vault), env=environment, capture_output=True, text=True,
                              encoding="utf-8", timeout=120)
        try:
            return proc, json.loads(proc.stdout).get("session_id")
        except (ValueError, TypeError):
            return proc, None

    command = ["codex", "-a", "never", "-s", "read-only", "exec"]
    if resume_session:
        command.append("resume")
    command += ["--dangerously-bypass-hook-trust", "--ignore-user-config", "--ignore-rules", "--json",
                "--skip-git-repo-check", "-o", str(output_path)]
    if resume_session:
        command += [resume_session, "-"]
    else:
        command += ["-C", str(vault), "-"]
    proc = subprocess.run(command, cwd=str(vault), env=environment, input=prompt, capture_output=True,
                          text=True, encoding="utf-8", timeout=120)
    session_id = None
    for line in proc.stdout.splitlines():
        try:
            event = json.loads(line)
        except (TypeError, ValueError):
            continue
        if event.get("type") == "thread.started" and isinstance(event.get("thread_id"), str):
            session_id = event["thread_id"]
            break
    return proc, session_id


def _ledger_terminal_counts(vault: Path) -> dict:
    path = vault / ".brain-eleven" / "capture" / "capture-ledger.jsonl"
    if not path.exists():
        return {}
    from collections import Counter

    actions = Counter(json.loads(line)["action"] for line in path.read_text(encoding="utf-8").splitlines() if line.strip())
    return dict(actions)


def _job_ids(vault: Path, status: str) -> set[str]:
    directory = vault / ".brain-eleven" / "capture" / status
    return {path.stem for path in directory.glob("*.json")} if directory.exists() else set()


def _verified_terminals(vault: Path, job_ids: set[str]) -> int:
    """Count new committed jobs only when their durable effects still exist."""
    from brain_eleven.runtime.worker import Worker, WorkerProcessingError

    worker = Worker(vault)
    count = 0
    for job_id in job_ids:
        path = vault / ".brain-eleven" / "capture" / "completed" / (job_id + ".json")
        try:
            job = json.loads(path.read_text(encoding="utf-8"))
            receipt = worker._read_receipt(job)
        except (OSError, ValueError, KeyError, TypeError, WorkerProcessingError):
            continue
        if receipt is not None:
            count += 1
    return count


def run(repetitions: int, client: str = "claude") -> Report:
    live_files = _live_files(client)
    before_hashes = _file_hashes(live_files)
    report = Report(client=client, client_version=_client_version(client), repo_head=_repo_head(),
                    live_settings_hash_before=json.dumps(before_hashes), live_settings_hash_after=None)

    with RetryingTemporaryDirectory(prefix="w07b-home-") as home_str, RetryingTemporaryDirectory(prefix="w07b-vault-") as vault_str:
        home, vault = Path(home_str), Path(vault_str)
        environment, settings_path = _prepare_client(client, home, vault)

        for n in range(1, repetitions + 1):
            prompt = PROMPTS[(n - 1) % len(PROMPTS)].format(n=n)
            before_revision = _memory_revision(vault)
            before_reviews = set((vault / ".brain-eleven" / "runtime" / "review").glob("*.json"))
            before_committed = _job_ids(vault, "completed")
            before_dead_letters = _job_ids(vault, "dead-letter")
            started = time.monotonic()
            proc, session_id = _invoke(client, vault, settings_path, environment, prompt, home / "last-message.txt")
            elapsed = time.monotonic() - started
            # Let the background service finish draining before inspecting terminal state.
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline:
                queued = list((vault / ".brain-eleven" / "capture" / "queued").glob("*.json")) if (vault / ".brain-eleven" / "capture" / "queued").exists() else []
                processing = list((vault / ".brain-eleven" / "capture" / "processing").glob("*.json")) if (vault / ".brain-eleven" / "capture" / "processing").exists() else []
                if not queued and not processing:
                    break
                time.sleep(0.5)
            review_dir = vault / ".brain-eleven" / "runtime" / "review"
            review_ids = sorted(p.stem for p in review_dir.glob("*.json")) if review_dir.exists() else []
            new_committed = _job_ids(vault, "completed") - before_committed
            new_reviews = set(review_dir.glob("*.json")) - before_reviews if review_dir.exists() else set()
            new_dead_letters = _job_ids(vault, "dead-letter") - before_dead_letters
            report.runs.append(RunResult(
                repetition=n, exit_code=proc.returncode, elapsed_s=round(elapsed, 3), session_id=session_id,
                ledger_terminal=_ledger_terminal_counts(vault), review_ids=review_ids,
                new_review_count=len(new_reviews), verified_terminal_count=_verified_terminals(vault, new_committed),
                dead_letter_count=len(new_dead_letters),
                memory_revision_before=before_revision, memory_revision_after=_memory_revision(vault),
            ))
        _stop_service(vault)
        report.live_settings_hash_after = json.dumps(_file_hashes(live_files))
    return report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--client", choices=("claude", "codex"), default="claude")
    parser.add_argument("--repetitions", type=int, default=2)
    parser.add_argument("--report", type=Path, default=None, help="optional path to write the JSON report")
    args = parser.parse_args(argv)

    report = run(args.repetitions, args.client)
    live_untouched = report.live_settings_hash_before == report.live_settings_hash_after
    payload = {
        "client": report.client,
        "client_version": report.client_version,
        "repo_head": report.repo_head,
        "live_global_settings_untouched": live_untouched,
        "runs": [
            {"repetition": r.repetition, "exit_code": r.exit_code, "elapsed_s": r.elapsed_s,
             "session_id_present": r.session_id is not None, "ledger_terminal_counts": r.ledger_terminal,
             "new_review_item_count": r.new_review_count,
             "verified_terminal_count": r.verified_terminal_count,
             "new_dead_letter_count": r.dead_letter_count,
             "memory_revision_unchanged": r.memory_revision_before == r.memory_revision_after}
            for r in report.runs
        ],
    }
    print(json.dumps(payload, indent=2))
    if args.report:
        args.report.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    if not live_untouched:
        print("FATAL: live global settings.json hash changed", file=sys.stderr)
        return 2
    ok = all(r.exit_code == 0 and r.session_id is not None
             and r.memory_revision_before == r.memory_revision_after
             and r.new_review_count > 0 and r.verified_terminal_count > 0
             and r.dead_letter_count == 0 for r in report.runs)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
