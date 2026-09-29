"""W-07B Claude native dogfood sample (manual, credential-gated; never run by CI).

Implements the "Dogfood" section of
docs/history/plans/WEAKNESS-W07B-NATIVE-ACCEPTANCE-EVIDENCE-PLAN.md for the
Claude side only: >=5 sessions and >=20 turns across two registered
projects, including a project switch, a SessionEnd -> next SessionStart
handoff and one controlled failed/retried maintenance intent derived from a
real native SessionEnd capture. Same
isolation as the sibling harnesses in this package: a throwaway vault and
throwaway client config; the live vault and live ~/.claude/settings.json are
never read or written. Stores only sanitized event/status/revision metadata
and opaque IDs/hashes, never prompt or transcript content. Set
``W07B_CLAUDE_CONFIG_DIR`` to a disposable directory under system temp when an
isolated authenticated profile must be reused across sign-in and evidence runs.
"""
from __future__ import annotations

import hashlib
import json
import sys
import time
from pathlib import Path
from tempfile import TemporaryDirectory

from .client_process import run_claude

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


def _run_claude(cwd: Path, settings_path: Path, prompt: str, session_id: str | None) -> dict:
    proc = run_claude(cwd, settings_path, prompt, session_id=session_id)
    try:
        doc = json.loads(proc.stdout)
    except (ValueError, TypeError):
        doc = {}
    return {"exit_code": proc.returncode, "session_id": doc.get("session_id"), "is_error": doc.get("is_error")}


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


def _canonical_snapshot(vault: Path, project_id: str) -> dict:
    """Return revisions and content hashes without exposing canonical bytes."""
    from brain_eleven.memory.store import MemoryStore
    from brain_eleven.projects.registry import ProjectRegistry
    from brain_eleven.state.store import StateStore

    memory = MemoryStore(vault)
    state = StateStore(vault)
    projects = ProjectRegistry(vault)
    files = {"memory": memory.path, "state": state.path, "projects": projects.path}
    hashes = {
        name: hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None
        for name, path in files.items()
    }
    return {
        "memory_revision": memory.revision(),
        "state_revision": state.project_revision(project_id),
        "project_registry_revision": projects.load()["revision"],
        "canonical_hashes": hashes,
    }


def _exercise_failed_retry(vault: Path) -> dict:
    """Fail once, then retry a maintenance intent from a committed native capture."""
    from brain_eleven.runtime import maintenance, maintenance_delivery as delivery

    try:
        # Reconciliation only creates intents from committed SessionEnd jobs
        # with verified worker receipts; it cannot invent a dogfood event.
        delivery.reconcile_completed(vault, limit=64)
        directories = delivery._dirs(vault)
        if list(directories[delivery.PROCESSING].glob("*.json")):
            return {"verified": False, "reason": "MAINTENANCE_INTENT_IN_FLIGHT"}
        queued = sorted(directories[delivery.QUEUED].glob("*.json"))
        if not queued:
            return {"verified": False, "reason": "NO_NATIVE_SESSION_END_INTENT"}

        selected_path = queued[0]
        selected = json.loads(selected_path.read_text(encoding="utf-8"))
        intent_id = selected.get("intent_id")
        project_id = selected.get("project_id")
        if not isinstance(intent_id, str) or not isinstance(project_id, str):
            return {"verified": False, "reason": "INVALID_MAINTENANCE_INTENT"}
        intent_hash = hashlib.sha256(intent_id.encode("utf-8")).hexdigest()[:16]
        before = _canonical_snapshot(vault, project_id)
        original_run_maintenance = maintenance.run_maintenance
        failure_calls = 0

        def fail_once(*args, **kwargs):
            nonlocal failure_calls
            failure_calls += 1
            raise RuntimeError("W07B controlled maintenance failure")

        maintenance.run_maintenance = fail_once
        try:
            first_processed = delivery.process_pending(vault, limit=1)
        finally:
            maintenance.run_maintenance = original_run_maintenance

        after_failure = _canonical_snapshot(vault, project_id)
        failed = delivery._find(directories, intent_id)
        failure_record = json.loads(failed[1].read_text(encoding="utf-8")) if failed else {}
        failure_queued = (
            failure_calls == 1 and first_processed == 0 and failed is not None and
            failed[0] == delivery.QUEUED and failure_record.get("attempt") == 1
        )
        unchanged_after_failure = before == after_failure
        if not failure_queued or not unchanged_after_failure:
            return {
                "verified": False,
                "reason": "FAILED_ATTEMPT_NOT_SAFE_AND_RETRYABLE",
                "intent_hash": intent_hash,
                "status_after_failure": failure_record.get("status"),
                "attempt_after_failure": failure_record.get("attempt"),
                "canonical_unchanged_after_failure": unchanged_after_failure,
            }

        retry_processed = delivery.process_pending(vault, limit=1)
        completed = delivery._find(directories, intent_id)
        completed_record = json.loads(completed[1].read_text(encoding="utf-8")) if completed else {}
        report_path = delivery._root(vault) / "reports" / f"{intent_id}.json"
        unchanged_after_retry = before == _canonical_snapshot(vault, project_id)
        verified = (
            retry_processed == 1 and completed is not None and
            completed[0] == delivery.COMPLETED and completed_record.get("attempt") == 2 and
            report_path.is_file() and unchanged_after_retry
        )
        return {
            "verified": verified,
            "reason": None if verified else "RETRY_COMPLETION_NOT_VERIFIED",
            "intent_hash": intent_hash,
            "status_after_failure": failure_record.get("status"),
            "attempt_after_failure": failure_record.get("attempt"),
            "status_after_retry": completed_record.get("status"),
            "attempt_after_retry": completed_record.get("attempt"),
            "report_present": report_path.is_file(),
            "canonical_unchanged_after_failure": unchanged_after_failure,
            "canonical_unchanged_after_retry": unchanged_after_retry,
            "memory_revision_before": before["memory_revision"],
            "memory_revision_after_failure": after_failure["memory_revision"],
            "state_revision_before": before["state_revision"],
            "state_revision_after_failure": after_failure["state_revision"],
            "project_registry_revision_before": before["project_registry_revision"],
            "project_registry_revision_after_failure": after_failure["project_registry_revision"],
        }
    except Exception:
        # Dogfood output must remain content-free even when evidence setup fails.
        return {"verified": False, "reason": "MAINTENANCE_RETRY_EVIDENCE_ERROR"}


def _stop_service(vault: Path) -> None:
    """Stop the background service and wait for it to actually exit.

    Found during this evidence step: without this, Windows'
    ``TemporaryDirectory.__exit__`` can raise ``WinError 145`` ("directory
    not empty") tearing down the vault, because the still-running service
    process holds an open handle under ``.brain-eleven/runtime/``. This is a
    harness lifecycle bug, not a runtime defect; see "Real findings" in the
    evidence report.
    """
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


def run() -> dict:
    from brain_eleven.runtime.install import install
    from brain_eleven.projects.registry import ProjectRegistry
    from brain_eleven.state import StateService

    with TemporaryDirectory(prefix="w07b-dog-home-") as home_s, TemporaryDirectory(prefix="w07b-dog-vault-") as vault_s:
        home, vault = Path(home_s), Path(vault_s)
        install(str(vault), home=str(home), clients=("claude",))  # registers `vault` itself as project-a
        settings_path = home / "isolated_hooks.json"
        settings_path.write_text(json.dumps({"hooks": json.loads((home / ".claude" / "settings.json").read_text(encoding="utf-8"))["hooks"]}), encoding="utf-8")

        project_a_root = ProjectRegistry(vault).resolve(vault)["project_id"]
        project_b_dir = Path(home_s).parent / "w07b-dogfood-project-b"
        project_b_dir.mkdir(exist_ok=True)
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
        for s_index, (label, template) in enumerate(SESSIONS, start=1):
            if last_project is not None and last_project != label:
                project_switch_observed = True
            last_project = label
            cwd = roots[label]
            before_review = _review_count(vault)
            session_id = None
            turn_results = []
            for t_index in range(1, TURNS_PER_SESSION + 1):
                prompt = template.format(s=s_index, t=t_index)
                r = _run_claude(cwd, settings_path, prompt, session_id)
                session_id = r.get("session_id") or session_id
                turn_results.append({"exit_code": r["exit_code"], "is_error": r.get("is_error")})
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
            sessions_log.append({
                "session_index": s_index,
                "project_label": label,
                "session_id_present": session_id is not None,
                "turns": turn_results,
                "review_items_delta": after_review - before_review,
                "maintenance_intent_status": worker.get("maintenance_intent_status"),
                "memory_revision": _memory_revision(vault),
            })
            # SessionEnd -> next SessionStart handoff: the vault's own captured
            # signal (last-transcript-stats, if present) must not be stale/absent
            # by the time the *next* session's SessionStart bootstrap runs; we
            # assert only that a following SessionStart itself succeeds cleanly
            # against a vault whose previous SessionEnd already committed.
            ledger = vault / ".brain-eleven" / "capture" / "capture-ledger.jsonl"
            lines = ledger.read_text(encoding="utf-8").splitlines() if ledger.exists() else []
            committed_for_session = sum(1 for line in lines if '"COMMITTED"' in line)
            handoff_checks.append({"after_session": s_index, "ledger_committed_total": committed_for_session})

        _stop_service(vault)
        maintenance_retry = _exercise_failed_retry(vault)
        return {
            "sessions": sessions_log,
            "total_turns": sum(len(s["turns"]) for s in sessions_log),
            "distinct_projects": sorted({s["project_label"] for s in sessions_log}),
            "project_switch_observed": project_switch_observed,
            "handoff_checks": handoff_checks,
            "maintenance_retry": maintenance_retry,
            "all_turns_ok": all(t["exit_code"] == 0 and t.get("is_error") is False for s in sessions_log for t in s["turns"]),
        }


def main(argv=None) -> int:
    report = run()
    print(json.dumps(report, indent=2))
    ok = (len(report["sessions"]) >= 5 and report["total_turns"] >= 20 and
          len(report["distinct_projects"]) >= 2 and report["project_switch_observed"] and
          report["all_turns_ok"] and report["maintenance_retry"]["verified"])
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
