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

Usage: ``python -m evals.w07b.native_smoke [--repetitions N]``
"""
from __future__ import annotations

import argparse
import hashlib
import json
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


@dataclass
class RunResult:
    repetition: int
    exit_code: int
    elapsed_s: float
    session_id: str | None
    ledger_terminal: dict
    review_ids: list
    memory_revision_before: int
    memory_revision_after: int


@dataclass
class Report:
    client_version: str
    repo_head: str
    live_settings_hash_before: str | None
    live_settings_hash_after: str | None
    runs: list = field(default_factory=list)


def _client_version() -> str:
    proc = subprocess.run(["claude", "--version"], capture_output=True, text=True, timeout=15)
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


def _ledger_terminal_counts(vault: Path) -> dict:
    path = vault / ".brain-eleven" / "capture" / "capture-ledger.jsonl"
    if not path.exists():
        return {}
    from collections import Counter

    actions = Counter(json.loads(line)["action"] for line in path.read_text(encoding="utf-8").splitlines() if line.strip())
    return dict(actions)


def run(repetitions: int) -> Report:
    from brain_eleven.runtime.install import install

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

        for n in range(1, repetitions + 1):
            prompt = PROMPTS[(n - 1) % len(PROMPTS)].format(n=n)
            cmd = ["claude", "-p", prompt, "--settings", str(isolated_path), "--setting-sources", "",
                   "--strict-mcp-config", "--tools", "", "--output-format", "json"]
            before_revision = _memory_revision(vault)
            started = time.monotonic()
            proc = subprocess.run(cmd, cwd=str(vault), capture_output=True, text=True, encoding="utf-8", timeout=120)
            elapsed = time.monotonic() - started
            session_id = None
            try:
                session_id = json.loads(proc.stdout).get("session_id")
            except (ValueError, TypeError):
                pass
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
            report.runs.append(RunResult(
                repetition=n, exit_code=proc.returncode, elapsed_s=round(elapsed, 3), session_id=session_id,
                ledger_terminal=_ledger_terminal_counts(vault), review_ids=review_ids,
                memory_revision_before=before_revision, memory_revision_after=_memory_revision(vault),
            ))
        report.live_settings_hash_after = _sha256(live_settings)
    return report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repetitions", type=int, default=2)
    parser.add_argument("--report", type=Path, default=None, help="optional path to write the JSON report")
    args = parser.parse_args(argv)

    report = run(args.repetitions)
    live_untouched = report.live_settings_hash_before == report.live_settings_hash_after
    payload = {
        "client_version": report.client_version,
        "repo_head": report.repo_head,
        "live_global_settings_untouched": live_untouched,
        "runs": [
            {"repetition": r.repetition, "exit_code": r.exit_code, "elapsed_s": r.elapsed_s,
             "session_id_present": r.session_id is not None, "ledger_terminal_counts": r.ledger_terminal,
             "review_item_count": len(r.review_ids),
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
    ok = all(r.exit_code == 0 and r.memory_revision_before == r.memory_revision_after and r.review_ids for r in report.runs)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
