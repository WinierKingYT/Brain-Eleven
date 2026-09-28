"""W-07B authenticated Codex smoke in an isolated temporary profile.

This harness stores Codex's transcript only in the caller-provided temporary
``CODEX_HOME`` so SessionEnd can resolve its native transcript locator. It
prints bounded event, queue and opaque review metadata only. The profile and
test vault must be removed after evidence capture.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

PROMPT_TEMPLATE = (
    "W07B isolated Codex smoke {n}: we decided to retain the atomic-write guard "
    "for codex-smoke-key-{n}. Answer briefly; do not use tools or run commands."
)
_SAFE_CODE = re.compile(r"^[A-Z0-9_]{1,64}$")


def _codex_home(value: str | None = None) -> Path:
    raw = value or os.environ.get("CODEX_HOME")
    if not raw:
        raise RuntimeError("CODEX_HOME_REQUIRED")
    home = Path(raw).resolve()
    default_home = (Path.home() / ".codex").resolve()
    temp_root = Path(__import__("tempfile").gettempdir()).resolve()
    try:
        common = Path(os.path.commonpath((str(home), str(temp_root))))
    except ValueError as exc:
        raise RuntimeError("CODEX_HOME_NOT_ISOLATED") from exc
    if home == default_home or common != temp_root:
        raise RuntimeError("CODEX_HOME_NOT_ISOLATED")
    return home


def _codex_environment(home: Path) -> dict[str, str]:
    env = os.environ.copy()
    env["CODEX_HOME"] = str(home)
    return env


def _parse_stream(output: str) -> dict:
    """Extract only the native thread ID and terminal turn state from JSONL."""
    thread_id = None
    turn_completed = False
    failure_code = None
    for line in output.splitlines():
        try:
            item = json.loads(line)
        except (TypeError, ValueError):
            continue
        event_type = item.get("type") if isinstance(item, dict) else None
        if event_type == "thread.started" and isinstance(item.get("thread_id"), str):
            thread_id = item["thread_id"]
        elif event_type == "turn.completed":
            turn_completed = True
        elif event_type in {"turn.failed", "error"}:
            raw = item.get("error")
            code = raw.get("code") if isinstance(raw, dict) else None
            failure_code = code.upper() if isinstance(code, str) and _SAFE_CODE.fullmatch(code.upper()) else "CLIENT_ERROR"
    return {"thread_id": thread_id, "turn_completed": turn_completed, "failure_code": failure_code}


def _read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def _memory_revision(vault: Path) -> int:
    path = vault / ".claude" / "validated-memory.json"
    return _read_json(path).get("revision", -1)


def _session_receipts(vault: Path, session_id: str) -> dict:
    from brain_eleven.runtime.storage import identity

    key = identity("session_", session_id)
    found = {}
    directory = vault / ".brain-eleven" / "runtime" / "deliveries"
    for path in directory.glob("*.json") if directory.exists() else ():
        doc = _read_json(path)
        if doc.get("client") == "codex" and doc.get("session_hash") == key:
            event = doc.get("event")
            if event in {"SessionStart", "UserPromptSubmit"}:
                found[event] = {"status": doc.get("status"), "stage": doc.get("stage"),
                                "context_delivered": doc.get("context_delivered") is True}
    return found


def _last_capture(vault: Path, session_id: str) -> dict:
    from brain_eleven.runtime.worker import capture_session_hash

    path = vault / ".brain-eleven" / "runtime" / "last-capture-codex.json"
    doc = _read_json(path)
    if doc.get("capture_session_hash") != capture_session_hash("codex", session_id):
        return {}
    outcome = doc.get("outcome")
    error = doc.get("error")
    safe_error = error if isinstance(error, str) and _SAFE_CODE.fullmatch(error) else None
    return {"outcome": outcome if isinstance(outcome, str) else None, "error_code": safe_error}


def _completed_job(vault: Path, session_id: str) -> dict:
    from brain_eleven.runtime.worker import capture_session_key

    session_key = capture_session_key("codex", session_id)
    directory = vault / ".brain-eleven" / "capture" / "completed"
    for path in directory.glob("*.json") if directory.exists() else ():
        doc = _read_json(path)
        event = doc.get("event")
        if isinstance(event, dict) and event.get("session_id") == session_key:
            return doc
    return {}


def _capture_receipt(vault: Path, job: dict) -> dict:
    """Read only the verified effect receipt bound to this terminal queue job."""
    job_id = job.get("job_id")
    event = job.get("event") if isinstance(job.get("event"), dict) else {}
    event_id = event.get("event_id")
    if not isinstance(job_id, str) or not job_id or not isinstance(event_id, str) or not event_id:
        return {}
    path = vault / ".brain-eleven" / "runtime" / "capture-receipts" / (job_id + ".json")
    receipt = _read_json(path)
    if (receipt.get("job_id") != job_id or receipt.get("event_id") != event_id
            or receipt.get("status") != "EFFECT_VERIFIED" or receipt.get("canonical_verified") is not True):
        return {}
    review_effect_ids = receipt.get("review_effect_ids")
    if (not isinstance(review_effect_ids, list) or len(review_effect_ids) > 10000
            or not all(isinstance(item, str) and item for item in review_effect_ids)):
        return {}
    return {"status": "EFFECT_VERIFIED", "review_effect_ids": review_effect_ids}


def _verified_review_id(vault: Path, session_id: str, marker: str, effect_ids: list[str]) -> str | None:
    from brain_eleven.runtime.review import ReviewStore
    from brain_eleven.runtime.storage import identity
    from brain_eleven.runtime.worker import capture_session_key

    expected_session = identity("session_", capture_session_key("codex", session_id))
    store = ReviewStore(vault)
    for review_id in effect_ids:
        try:
            item = _read_json(store.path(review_id))
        except ValueError:
            continue
        source = item.get("source") if isinstance(item.get("source"), dict) else {}
        candidate = item.get("candidate") if isinstance(item.get("candidate"), dict) else {}
        content = candidate.get("content") or candidate.get("text") or ""
        if (item.get("status") == "PENDING" and source.get("client") == "codex"
                and source.get("session_hash") == expected_session
                and isinstance(content, str) and marker.casefold() in content.casefold()):
            return review_id
    return None


def _wait_for_capture(vault: Path, session_id: str, timeout: float = 25.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = _completed_job(vault, session_id)
        if job:
            return job
        time.sleep(0.1)
    return {}


def _client_version(env: dict[str, str]) -> str:
    proc = subprocess.run(["codex", "--version"], capture_output=True, text=True,
                          encoding="utf-8", timeout=15, env=env)
    match = re.search(r"\d+\.\d+\.\d+(?:[-+][A-Za-z0-9.-]+)?", proc.stdout + " " + proc.stderr)
    return match.group(0) if match else "unknown"


def _repo_head() -> str:
    proc = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO,
                          capture_output=True, text=True, timeout=15)
    return proc.stdout.strip()


def _stop_service(vault: Path) -> None:
    from .latency_matrix import _stop_service as stop

    stop(vault)


def run(vault: Path, repetitions: int = 2) -> dict:
    from brain_eleven.runtime.install import install
    from brain_eleven.runtime.worker import capture_session_hash

    if repetitions < 1:
        raise ValueError("repetitions must be positive")
    home = _codex_home()
    vault = Path(vault).resolve()
    if os.path.commonpath((str(vault), str(home.parent))) != str(home.parent):
        raise RuntimeError("VAULT_NOT_ISOLATED")
    env = _codex_environment(home)
    install(str(vault), home=str(home.parent), clients=("codex",))
    version = _client_version(env)
    runs = []
    try:
        for n in range(1, repetitions + 1):
            _stop_service(vault)
            prompt = PROMPT_TEMPLATE.format(n=n)
            marker = f"codex-smoke-key-{n}"
            revision_before = _memory_revision(vault)
            started = time.monotonic()
            try:
                proc = subprocess.run(
                    ["codex", "exec", "--json", "--sandbox", "read-only", "--cd", str(vault), prompt],
                    cwd=str(vault), capture_output=True, text=True, encoding="utf-8", timeout=120, env=env,
                )
                parsed = _parse_stream(proc.stdout)
                exit_code = proc.returncode
            except subprocess.TimeoutExpired:
                parsed = {"thread_id": None, "turn_completed": False, "failure_code": "TIMEOUT"}
                exit_code = 124
            elapsed_ms = round((time.monotonic() - started) * 1000)
            session_id = parsed.get("thread_id")
            job = _wait_for_capture(vault, session_id) if session_id else {}
            receipts = _session_receipts(vault, session_id) if session_id else {}
            capture = _last_capture(vault, session_id) if session_id else {}
            effect_receipt = _capture_receipt(vault, job) if job else {}
            effect_ids = effect_receipt.get("review_effect_ids", [])
            review_id = _verified_review_id(vault, session_id, marker, effect_ids) if session_id else None
            revision_after = _memory_revision(vault)
            checks = {
                "session_start_delivered": receipts.get("SessionStart", {}).get("stage") == "DELIVERED",
                "user_prompt_submit_delivered": receipts.get("UserPromptSubmit", {}).get("stage") == "DELIVERED",
                "queue_committed": job.get("status") == "COMMITTED",
                "capture_receipt_verified": effect_receipt.get("status") == "EFFECT_VERIFIED",
                "review_effect_verified": review_id is not None,
                "memory_revision_unchanged": revision_before == revision_after,
            }
            failure_code = parsed.get("failure_code")
            if not failure_code:
                for name, passed in checks.items():
                    if not passed:
                        failure_code = {
                            "session_start_delivered": "SESSIONSTART_NOT_DELIVERED",
                            "user_prompt_submit_delivered": "USERPROMPT_NOT_DELIVERED",
                            "queue_committed": capture.get("error_code") or "CAPTURE_NOT_TERMINAL",
                            "capture_receipt_verified": "CAPTURE_RECEIPT_NOT_VERIFIED",
                            "review_effect_verified": "EXPECTED_REVIEW_EFFECT_MISSING",
                            "memory_revision_unchanged": "CANONICAL_REVISION_CHANGED",
                        }[name]
                        break
            ok = exit_code == 0 and parsed.get("turn_completed") is True and all(checks.values())
            runs.append({
                "exit_code": exit_code,
                "turn_completed": parsed.get("turn_completed") is True,
                "session_hash": capture_session_hash("codex", session_id) if session_id else None,
                "elapsed_ms": elapsed_ms,
                "hook_receipts": receipts,
                "capture_outcome": capture.get("outcome"),
                "queue_event_id": (job.get("event") or {}).get("event_id") if job else None,
                "queue_terminal_state": job.get("status") if job else None,
                "capture_receipt_status": effect_receipt.get("status"),
                "review_effect_id": review_id,
                **checks,
                "failure_code": None if ok else failure_code or "CLIENT_ERROR",
                "verified": ok,
            })
    finally:
        _stop_service(vault)
    return {
        "client": "codex",
        "client_version": version,
        "implementation_head": _repo_head(),
        "harness_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "isolated_codex_home": True,
        "runs": runs,
        "trust_verdict": "VERIFIED" if runs and all(item["verified"] for item in runs) else "BOUNDED_UNVERIFIED_CODEX",
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vault", type=Path, required=True)
    parser.add_argument("--repetitions", type=int, default=2)
    args = parser.parse_args(argv)
    try:
        report = run(args.vault, args.repetitions)
    except (OSError, RuntimeError, ValueError) as exc:
        code = str(exc) if _SAFE_CODE.fullmatch(str(exc)) else "HARNESS_ERROR"
        print(json.dumps({"client": "codex", "trust_verdict": "BOUNDED_UNVERIFIED_CODEX",
                          "failure_code": code, "runs": []}, indent=2))
        return 1
    print(json.dumps(report, indent=2))
    return 0 if report["trust_verdict"] == "VERIFIED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
