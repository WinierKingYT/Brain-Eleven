#!/usr/bin/env python3
"""Truthful, lineage-aware execution contract for the SessionEnd pipeline.

The hook is a convenience layer: individual failures never corrupt canonical
memory or prevent Claude from ending a session.  They are nevertheless never
reported as success because an older derived artifact happens to exist.
"""

import argparse
import hashlib
import json
import os
import subprocess  # nosec B404 - runs only this repository's fixed scripts.
import sys
import tempfile
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from memory_store import MemoryStore, MemoryStoreError


SUCCESS = "SUCCESS"
DEGRADED = "DEGRADED"
FAILED = "FAILED"
SKIPPED = "SKIPPED"
RESULT_SCHEMA_VERSION = 1


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _new_run_id() -> str:
    return f"run_{datetime.now(timezone.utc):%Y%m%dT%H%M%S%fZ}_{uuid.uuid4().hex[:10]}"


def _atomic_write_json(path: Path, document: Dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(document, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        Path(temporary_name).replace(path)
    finally:
        temporary = Path(temporary_name)
        if temporary.exists():
            temporary.unlink()


def _file_snapshot(path: Path) -> Optional[Dict[str, object]]:
    if not path.is_file():
        return None
    stat = path.stat()
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return {"mtime_ns": stat.st_mtime_ns, "size": stat.st_size, "sha256": digest}


def _canonical_revision(vault_path: Path) -> Tuple[Optional[int], Optional[str]]:
    try:
        return MemoryStore(vault_path).revision(), None
    except MemoryStoreError as exc:
        return None, str(exc)


def _validate_json_artifact(path: Path, run_id: str, expected_revision: Optional[int]) -> Optional[str]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return f"artifact is not valid JSON: {exc}"
    if not isinstance(document, dict):
        return "artifact must be a JSON object"
    if document.get("generated_by_run") != run_id and document.get("last_validated_by_run") != run_id:
        return "artifact lineage does not match this run"
    source_revision = document.get("source_memory_revision")
    if source_revision is not None and expected_revision is not None and source_revision != expected_revision:
        return f"artifact revision {source_revision} does not match {expected_revision}"
    return None


@dataclass(frozen=True)
class StepSpec:
    name: str
    command: Sequence[str]
    artifact: Path
    critical: bool = False


def _skipped_step(spec: StepSpec, run_id: str, revision: Optional[int], reason: str) -> Dict:
    now = _utc_now()
    return {
        "step": spec.name,
        "run_id": run_id,
        "started_at": now,
        "finished_at": now,
        "exit_code": None,
        "status": SKIPPED,
        "source_memory_revision": revision,
        "produced_memory_revision": revision,
        "artifact": str(spec.artifact),
        "artifact_created_this_run": False,
        "error": reason,
    }


def _run_step(spec: StepSpec, vault_path: Path, run_id: str) -> Dict:
    source_revision, revision_error = _canonical_revision(vault_path)
    before = _file_snapshot(spec.artifact)
    started_at = _utc_now()
    started_ns = time.time_ns()
    process_error = None
    exit_code = None
    try:
        completed = subprocess.run(  # nosec B603 - StepSpec commands are fixed by this module.
            list(spec.command),
            cwd=vault_path,
            text=True,
            capture_output=True,
            check=False,
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        )
        exit_code = completed.returncode
        if completed.returncode:
            output = (completed.stderr or completed.stdout).strip()[-1000:]
            process_error = f"command exited {completed.returncode}: {output or 'no output'}"
    except OSError as exc:
        process_error = f"command could not start: {exc}"

    after = _file_snapshot(spec.artifact)
    produced_revision, produced_revision_error = _canonical_revision(vault_path)
    fresh_artifact = bool(after and after["mtime_ns"] >= started_ns)
    validation_error = None
    if exit_code == 0 and fresh_artifact:
        validation_error = _validate_json_artifact(spec.artifact, run_id, produced_revision)

    error = process_error or revision_error or produced_revision_error
    if exit_code == 0 and not fresh_artifact:
        error = "command succeeded but did not create a fresh artifact for this run"
    if validation_error:
        error = validation_error

    succeeded = exit_code == 0 and fresh_artifact and not error
    status = SUCCESS if succeeded else (FAILED if spec.critical else DEGRADED)
    return {
        "step": spec.name,
        "run_id": run_id,
        "started_at": started_at,
        "finished_at": _utc_now(),
        "exit_code": exit_code,
        "status": status,
        "source_memory_revision": source_revision,
        "produced_memory_revision": produced_revision,
        "artifact": str(spec.artifact),
        "artifact_created_this_run": fresh_artifact,
        "artifact_changed": before != after,
        "error": error,
    }


def run_pipeline(vault_path: Path, project_root: Path, python_executable: str, run_id: str = None) -> Dict:
    """Run SessionEnd steps and atomically persist their truthful outcome."""
    vault_path = Path(vault_path).resolve()
    project_root = Path(project_root).resolve()
    run_id = run_id or _new_run_id()
    scripts = vault_path / "scripts"
    artifacts = vault_path / ".claude"
    compiler = StepSpec(
        "memory_compiler",
        [python_executable, str(scripts / "memory-compiler.py"), "--vault", str(vault_path), "--generated-by-run", run_id],
        artifacts / "compiled-memory.json",
    )
    validator = StepSpec(
        "memory_validator",
        [python_executable, str(scripts / "memory-validator.py"), "--vault", str(vault_path), "--generated-by-run", run_id],
        artifacts / "validated-memory.json",
        critical=True,
    )
    context = StepSpec(
        "context_compiler",
        [
            python_executable,
            str(scripts / "context-compiler.py"),
            "--vault",
            str(vault_path),
            "--project-root",
            str(project_root),
            "--generated-by-run",
            run_id,
        ],
        artifacts / "context-bootstrap.json",
    )
    maintenance = StepSpec(
        "post_session_maintenance",
        [python_executable, str(scripts / "post_session_maintenance.py"), "--vault", str(vault_path), "--generated-by-run", run_id, "--quiet"],
        artifacts / "session-maintenance-report.json",
    )

    started_at = _utc_now()
    initial_revision, initial_error = _canonical_revision(vault_path)
    steps: List[Dict] = []
    first = _run_step(compiler, vault_path, run_id)
    steps.append(first)
    if first["status"] == SUCCESS:
        second = _run_step(validator, vault_path, run_id)
    else:
        second = _skipped_step(validator, run_id, initial_revision, "compiler did not produce a fresh candidate artifact")
    steps.append(second)
    if second["status"] == SUCCESS:
        steps.append(_run_step(context, vault_path, run_id))
    else:
        steps.append(_skipped_step(context, run_id, initial_revision, "canonical validation did not succeed"))
    steps.append(_run_step(maintenance, vault_path, run_id))

    final_revision, final_error = _canonical_revision(vault_path)
    statuses = {step["status"] for step in steps}
    overall = FAILED if FAILED in statuses else (DEGRADED if DEGRADED in statuses else SUCCESS)
    result = {
        "schema_version": RESULT_SCHEMA_VERSION,
        "run_id": run_id,
        "started_at": started_at,
        "finished_at": _utc_now(),
        "status": overall,
        "source_memory_revision": initial_revision,
        "produced_memory_revision": final_revision,
        "revision_error": initial_error or final_error,
        "steps": steps,
    }
    history_path = artifacts / "session-runs" / f"{run_id}.json"
    _atomic_write_json(history_path, result)
    _atomic_write_json(artifacts / "session-run-result.json", result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the truthful Brain-Eleven SessionEnd pipeline")
    parser.add_argument("--vault", required=True)
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--run-id", default=None)
    args = parser.parse_args()
    result = run_pipeline(Path(args.vault), Path(args.project_root), args.python, args.run_id)
    print(json.dumps({"run_id": result["run_id"], "status": result["status"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
