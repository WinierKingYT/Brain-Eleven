"""CAPTURE_SILENT_GAP audit: transcripts vs. capture ledger (read-only)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from capture_gap_audit import audit, main, verdict  # noqa: E402
from brain_eleven.projects.registry import ProjectRegistry  # noqa: E402
from brain_eleven.runtime.migration import migrate  # noqa: E402
from brain_eleven.runtime.ownership import _project_slug  # noqa: E402
from brain_eleven.runtime.storage import RuntimeConfig, write_json  # noqa: E402
from brain_eleven.runtime.worker import capture_session_hash, enqueue  # noqa: E402


def _h(value: str) -> str:
    return capture_session_hash("claude", value)


def _setup(tmp_path, sessions, ledger):
    vault, home = tmp_path / "vault", tmp_path / "claude"
    (vault / ".claude").mkdir(parents=True)
    (vault / ".brain-eleven" / "capture").mkdir(parents=True)
    projects = []
    for pid, root in (("p_a", str(tmp_path / "proj_a")), ("p_b", str(tmp_path / "projb"))):
        projects.append({"project_id": pid, "root": root})
        directory = home / "projects" / _project_slug(root)
        directory.mkdir(parents=True)
        for sid in sessions.get(pid, []):
            (directory / f"{sid}.jsonl").write_text("{}\n", encoding="utf-8")
    (vault / ".claude" / "project-registry.json").write_text(json.dumps({"projects": projects}))
    lines = [json.dumps({"event_type": "SESSION_END", "session_id_hash": _h(sid), "project_id": pid,
                         "action": action, **({"error_code": code} if code else {})})
             for sid, pid, action, code in ledger]
    (vault / ".brain-eleven" / "capture" / "capture-ledger.jsonl").write_text("\n".join(lines) + "\n")
    return vault, home


def _ok(sid, pid):
    return [(sid, pid, "ENQUEUED", None), (sid, pid, "COMMITTED", None)]


def test_pass_when_every_session_committed(tmp_path):
    sessions = {"p_a": [f"a{i}" for i in range(10)], "p_b": [f"b{i}" for i in range(10)]}
    ledger = [row for pid, sids in sessions.items() for sid in sids for row in _ok(sid, pid)]
    vault, home = _setup(tmp_path, sessions, ledger)
    report = audit(vault, home)
    assert report["totals"]["committed"] == 20
    assert verdict(report, min_projects=2, min_sessions=20) == "PASS"
    assert main(["--vault", str(vault), "--claude-home", str(home)]) == 0


def test_missing_enqueue_and_dead_letter_fail(tmp_path):
    sessions = {"p_a": ["a1", "a2"], "p_b": ["b1"]}
    ledger = _ok("a1", "p_a") + [("b1", "p_b", "ENQUEUED", None),
                                 ("b1", "p_b", "DEAD_LETTER", "TRANSCRIPT_OWNERSHIP_UNVERIFIED")]
    vault, home = _setup(tmp_path, sessions, ledger)
    report = audit(vault, home)
    assert report["totals"]["missing"] == 1
    assert report["totals"]["dead_letter"] == 1
    assert report["dead_letter_error_codes"] == {"TRANSCRIPT_OWNERSHIP_UNVERIFIED": 1}
    assert verdict(report, min_projects=2, min_sessions=1) == "FAIL"


def test_too_few_sessions_is_insufficient_not_pass(tmp_path):
    sessions = {"p_a": ["a1"], "p_b": ["b1"]}
    vault, home = _setup(tmp_path, sessions, _ok("a1", "p_a") + _ok("b1", "p_b"))
    assert verdict(audit(vault, home), min_projects=2, min_sessions=20) == "INSUFFICIENT_EVIDENCE"


def test_bootstrap_receipts_are_joined_per_session(tmp_path):
    sessions = {"p_a": ["a1", "a2", "a3"]}
    vault, home = _setup(tmp_path, sessions, [r for s in ("a1", "a2", "a3") for r in _ok(s, "p_a")])
    deliveries = vault / ".brain-eleven" / "runtime" / "deliveries"
    deliveries.mkdir(parents=True)
    for name, sid, stage, reason in (("d1", "a1", "DELIVERED", None),
                                     ("d2", "a2", "COMPILED_NOT_DELIVERED", "EMPTY_CONTEXT")):
        (deliveries / f"{name}.json").write_text(json.dumps({
            "event": "SessionStart", "at": "2026-09-25T00:00:00Z", "stage": stage, "reason": reason,
            "capture_session_hash": _h(sid)}))
    report = audit(vault, home)
    assert report["bootstrap_receipts"] == {"DELIVERED": 1, "COMPILED_NOT_DELIVERED:EMPTY_CONTEXT": 1,
                                            "NO_RECEIPT": 1}


def test_real_native_enqueue_is_seen_by_the_audit(tmp_path):
    """Regression: the audit must match what worker.enqueue actually writes
    (hashed ``claude:<sha256>`` session key, ``SESSION_END`` event type)."""
    vault, home = tmp_path / "vault", tmp_path / "claude"
    vault.mkdir()
    project = ProjectRegistry(vault).register(vault, proactive_capture=True)
    migrate(vault)
    write_json(RuntimeConfig(vault).path, {
        "schema_version": 1, "mode": "CANARY", "project_ids": [project["project_id"]],
        "local_model": None, "transcript_roots": {"claude": [str(home)], "codex": [str(home)]}})
    directory = home / "projects" / _project_slug(project["root"])
    directory.mkdir(parents=True)
    for sid in ("real-1", "real-2"):
        path = directory / f"{sid}.jsonl"
        path.write_text(json.dumps({"type": "user", "sessionId": sid}) + "\n", encoding="utf-8")
        if sid == "real-1":
            enqueue(vault, "claude", {"session_id": sid, "cwd": str(vault), "transcript_path": str(path)})
    report = audit(vault, home)
    assert report["totals"]["sessions"] == 2
    assert report["totals"]["enqueued"] == 1 and report["totals"]["missing"] == 1


def test_later_committed_job_recovers_an_earlier_dead_letter(tmp_path):
    sessions = {"p_a": ["a1"], "p_b": ["b1"]}
    ledger = [("a1", "p_a", "ENQUEUED", None), ("a1", "p_a", "DEAD_LETTER", "TRANSCRIPT_CHANGED"),
              ("a1", "p_a", "ENQUEUED", None), ("a1", "p_a", "COMMITTED", None)] + _ok("b1", "p_b")
    vault, home = _setup(tmp_path, sessions, ledger)
    report = audit(vault, home)
    assert report["totals"]["dead_letter"] == 0 and report["totals"]["dead_letter_recovered"] == 1
    assert report["totals"]["committed"] == 2
