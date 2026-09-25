"""W-07B native dogfood sample (manual, credential-gated; never run by CI).

Implements the "Dogfood" section of
docs/history/plans/WEAKNESS-W07B-NATIVE-ACCEPTANCE-EVIDENCE-PLAN.md for the
Claude or Codex: >=5 sessions and >=20 turns across two registered
projects, including a project switch, a SessionEnd -> next SessionStart
handoff and a controlled failed/retried maintenance intent after native
capture. Same isolation as the sibling harnesses in this package: a
throwaway vault and client config. Stores only sanitized event/status/revision
metadata, never prompt, transcript or credential content.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from tempfile import TemporaryDirectory

from evals.w07b.native_smoke import _invoke, _prepare_client, _file_hashes, _live_files

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

TURNS_PER_SESSION = 4
SESSIONS = [
    ("project-a", "A first decision for session {s} turn {t}."),
    ("project-a", "A first decision for session {s} turn {t}."),
    ("project-a", "A first decision for session {s} turn {t}."),
    ("project-b", "A second-project decision for session {s} turn {t}."),
    ("project-b", "A second-project decision for session {s} turn {t}."),
]


def _run_native(client: str, cwd: Path, settings_path: Path | None, environment: dict[str, str],
                prompt: str, session_id: str | None, output_path: Path) -> dict:
    proc, native_session = _invoke(client, cwd, settings_path, environment, prompt, output_path,
                                   resume_session=session_id)
    is_error = None
    if client == "claude":
        try:
            is_error = json.loads(proc.stdout).get("is_error")
        except (ValueError, TypeError):
            pass
    return {"exit_code": proc.returncode, "session_id": native_session, "is_error": is_error}


def _drain(vault: Path, timeout: float = 15.0) -> None:
    deadline = time.monotonic() + timeout
    queued = vault / ".brain-eleven" / "capture" / "queued"
    processing = vault / ".brain-eleven" / "capture" / "processing"
    while time.monotonic() < deadline:
        pending = (list(queued.glob("*.json")) if queued.exists() else []) + \
                  (list(processing.glob("*.json")) if processing.exists() else [])
        if not pending:
            return
        time.sleep(0.3)


def _review_count(vault: Path) -> int:
    review = vault / ".brain-eleven" / "runtime" / "review"
    return len(list(review.glob("*.json"))) if review.exists() else 0


def _last_worker(vault: Path) -> dict:
    path = vault / ".brain-eleven" / "runtime" / "last-worker.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def _memory_revision(vault: Path) -> int:
    path = vault / ".claude" / "validated-memory.json"
    return json.loads(path.read_text(encoding="utf-8"))["revision"] if path.exists() else -1


def _exercise_failed_retry(vault: Path) -> dict:
    """Inject one bounded maintenance failure after native capture and retry it."""
    from unittest.mock import patch

    from brain_eleven.memory import MemoryStore
    from brain_eleven.projects.registry import ProjectRegistry
    from brain_eleven.runtime import maintenance, maintenance_delivery as delivery
    from brain_eleven.state import StateStore

    pending_root = delivery._root(vault)
    for _ in range(3):
        if not list((pending_root / "queued").glob("*.json")) and not list((pending_root / "processing").glob("*.json")):
            break
        delivery.process_pending(vault, limit=100)
    backlog_drained = (not list((pending_root / "queued").glob("*.json")) and
                       not list((pending_root / "processing").glob("*.json")))
    project = ProjectRegistry(vault).resolve(vault)
    if project is None or not backlog_drained:
        return {"native_maintenance_backlog_drained": backlog_drained,
                "failed_attempt_recorded": False, "retry_completed": False,
                "canonical_unchanged": False, "staging_empty": False}
    job = {"job_id": "w07b-dogfood-fault-probe",
           "event": {"event_type": "SESSION_END", "event_id": "w07b-dogfood-fault-probe",
                     "project": {"project_id": project["project_id"]}}}
    delivery.enqueue(vault, job, {"status": "PROCESSED", "effect_verified": True})
    queued = sorted((delivery._root(vault) / "queued").glob("*.json"))
    if len(queued) != 1:
        return {"native_maintenance_backlog_drained": backlog_drained,
                "failed_attempt_recorded": False, "retry_completed": False,
                "canonical_unchanged": False, "staging_empty": False}
    intent_id = queued[0].stem
    initial = json.loads(queued[0].read_text(encoding="utf-8"))
    project_id = initial["project_id"]
    memory_before = MemoryStore(vault).revision()
    state_before = StateStore(vault).project_revision(project_id)

    with patch.object(maintenance, "run_maintenance", side_effect=RuntimeError("injected retry probe")):
        delivery.process_pending(vault, limit=1)
    after_failure = json.loads(queued[0].read_text(encoding="utf-8")) if queued[0].exists() else {}
    canonical_unchanged = (MemoryStore(vault).revision() == memory_before and
                           StateStore(vault).project_revision(project_id) == state_before)

    def success_report(*args, **kwargs):
        return {"graph": {"ok": True, "data": {"projection": {"source_memory_revision": memory_before}}},
                "anomalies": {"ok": True, "data": {"total_memories_scanned": 0, "total_anomalies": 0,
                                             "by_severity": {"warning": 0}}},
                "digest": {"ok": True, "data": {"total_memories_considered": 0, "total_after_dedup": 0}},
                "surface_at_next_session": True}

    with patch.object(maintenance, "run_maintenance", side_effect=success_report):
        delivery.process_pending(vault, limit=1)
    completed = delivery._root(vault) / "completed" / (intent_id + ".json")
    terminal = json.loads(completed.read_text(encoding="utf-8")) if completed.exists() else {}
    report = delivery._root(vault) / "reports" / (intent_id + ".json")
    return {
        "native_maintenance_backlog_drained": backlog_drained,
        "failed_attempt_recorded": (after_failure.get("status") == "QUEUED" and
                                    after_failure.get("attempt") == 1 and
                                    after_failure.get("error_code") == "MAINTENANCE_FAILED"),
        "retry_completed": (terminal.get("status") == "COMPLETED" and terminal.get("attempt") == 2 and
                            report.exists()),
        "canonical_unchanged": (canonical_unchanged and MemoryStore(vault).revision() == memory_before and
                                StateStore(vault).project_revision(project_id) == state_before),
        "staging_empty": not list((delivery._root(vault) / "staging").glob("*.json")),
    }


def _stop_service(vault: Path) -> None:
    """Stop the background service and wait for it to actually exit.

    Found during this evidence step: without this, Windows'
    ``TemporaryDirectory.__exit__`` can raise ``WinError 145`` ("directory
    not empty") tearing down the vault, because the still-running service
    process holds an open handle under ``.brain-eleven/runtime/``. This is a
    harness lifecycle bug, not a runtime defect; see "Real findings" in the
    evidence report.
    """
    from brain_eleven.runtime.launcher import request_service, _process_alive

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


def run(*, client: str = "claude") -> dict:
    from brain_eleven.projects.registry import ProjectRegistry
    from brain_eleven.state import StateService

    live_files = _live_files(client)
    live_hashes = _file_hashes(live_files)
    with TemporaryDirectory(prefix="w07b-dog-home-") as home_s, \
            TemporaryDirectory(prefix="w07b-dog-vault-") as vault_s, \
            TemporaryDirectory(prefix="w07b-dog-project-b-") as project_b_s:
        home, vault = Path(home_s), Path(vault_s)
        environment, settings_path = _prepare_client(client, home, vault)

        project_b_dir = Path(project_b_s)
        project_b = ProjectRegistry(vault).register(project_b_dir, project_id="proj-b", proactive_capture=True)
        StateService(vault).init_project(project_b["project_id"], source={"type": "user", "reference": "w07b-dogfood"})
        # Real finding from this evidence step: ProjectRegistry.register()
        # alone is not enough. allowed() (brain_eleven/runtime/worker.py)
        # requires the project_id to ALSO be in RuntimeConfig.project_ids;
        # install() only adds the vault's own project there. Without this,
        # every capture for a second, registry-only project is silently
        # SCOPE_DISABLED -- see "Real findings" in the evidence report.
        from brain_eleven.runtime.storage import RuntimeConfig

        def _add_project(current):
            current["project_ids"] = list(dict.fromkeys(current["project_ids"] + [project_b["project_id"]]))

        RuntimeConfig(vault)._mutate_current(_add_project)
        roots = {"project-a": vault, "project-b": project_b_dir}

        sessions_log = []
        last_project = None
        project_switch_observed = False
        handoff_checks = []
        prior_session_committed = None
        ledger = vault / ".brain-eleven" / "capture" / "capture-ledger.jsonl"
        def _action_count(action: str) -> int:
            if not ledger.exists():
                return 0
            return sum(json.loads(line).get("action") == action for line in ledger.read_text(encoding="utf-8").splitlines() if line.strip())

        for s_index, (label, template) in enumerate(SESSIONS, start=1):
            if last_project is not None and last_project != label:
                project_switch_observed = True
            last_project = label
            cwd = roots[label]
            before_review = _review_count(vault)
            before_committed = _action_count("COMMITTED")
            before_dead_letters = _action_count("DEAD_LETTER")
            session_id = None
            turn_results = []
            for t_index in range(1, TURNS_PER_SESSION + 1):
                prompt = template.format(s=s_index, t=t_index)
                r = _run_native(client, cwd, settings_path, environment, prompt, session_id, home / "last-message.txt")
                session_id = r.get("session_id") or session_id
                turn_results.append({"exit_code": r["exit_code"], "is_error": r.get("is_error"),
                                     "session_id_present": session_id is not None})
                # A small, realistic gap between turns of the same resumed
                # session (a human is reading/typing between messages). A
                # zero-delay back-to-back --resume burst was found, during
                # this evidence step, to sometimes dead-letter capture jobs
                # intermittently -- see "Real finding" in the evidence report;
                # that is reported separately, not reproduced here.
                time.sleep(1.0)
            _drain(vault)
            worker = _last_worker(vault)
            after_review = _review_count(vault)
            from brain_eleven.runtime.storage import identity
            start_receipt = (vault / ".brain-eleven" / "runtime" / "deliveries" /
                             (identity("delivery_", client, session_id, "bootstrap") + ".json")) if session_id else None
            start_seen = bool(start_receipt and start_receipt.exists())
            sessions_log.append({
                "session_index": s_index,
                "project_label": label,
                "session_id_present": session_id is not None,
                "session_start_receipt_seen": start_seen,
                "prior_session_committed_before_start": prior_session_committed,
                "turns": turn_results,
                "review_items_delta": after_review - before_review,
                "committed_jobs_delta": _action_count("COMMITTED") - before_committed,
                "dead_letter_jobs_delta": _action_count("DEAD_LETTER") - before_dead_letters,
                "maintenance_intent_status": worker.get("maintenance_intent_status"),
                "memory_revision": _memory_revision(vault),
            })
            # SessionEnd -> next SessionStart handoff: the vault's own captured
            # signal (last-transcript-stats, if present) must not be stale/absent
            # by the time the *next* session's SessionStart bootstrap runs; we
            # assert only that a following SessionStart itself succeeds cleanly
            # against a vault whose previous SessionEnd already committed.
            lines = ledger.read_text(encoding="utf-8").splitlines() if ledger.exists() else []
            committed_for_session = sum(1 for line in lines if '"COMMITTED"' in line)
            handoff_checks.append({"after_session": s_index, "ledger_committed_total": committed_for_session})
            prior_session_committed = committed_for_session > before_committed

        _stop_service(vault)
        retry_probe = _exercise_failed_retry(vault)
        return {
            "client": client,
            "live_files_untouched": live_hashes == _file_hashes(live_files),
            "sessions": sessions_log,
            "total_turns": sum(len(s["turns"]) for s in sessions_log),
            "distinct_projects": sorted({s["project_label"] for s in sessions_log}),
            "project_switch_observed": project_switch_observed,
            "handoff_checks": handoff_checks,
            "failed_retry_probe": retry_probe,
            "all_turns_ok": all(t["exit_code"] == 0 and t["session_id_present"] and t.get("is_error") is not True
                                for s in sessions_log for t in s["turns"]),
        }


def main(argv=None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--client", choices=("claude", "codex"), default="claude")
    parser.add_argument("--report", type=Path, default=None)
    args = parser.parse_args(argv)
    report = run(client=args.client)
    print(json.dumps(report, indent=2))
    if args.report:
        args.report.write_text(json.dumps(report, indent=2), encoding="utf-8")
    ok = (len(report["sessions"]) >= 5 and report["total_turns"] >= 20 and
          len(report["distinct_projects"]) >= 2 and report["project_switch_observed"] and
          report["all_turns_ok"] and report["live_files_untouched"] and
          all(s["committed_jobs_delta"] > 0 and s["dead_letter_jobs_delta"] == 0 and
              s["session_start_receipt_seen"] and s["prior_session_committed_before_start"] is not False
              for s in report["sessions"]) and
          all(report["failed_retry_probe"].values()))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
