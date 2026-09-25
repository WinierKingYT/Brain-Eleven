"""CAPTURE_SILENT_GAP audit: transcripts vs. capture ledger (read-only)."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from capture_gap_audit import audit, main, verdict  # noqa: E402
from brain_eleven.runtime.ownership import _project_slug  # noqa: E402


def _h(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


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
    lines = [json.dumps({"event_type": "SessionEnd", "session_id_hash": _h(sid), "project_id": pid,
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
