#!/usr/bin/env python3
"""Run pip-audit with truthful CI outcomes and a machine-readable report."""

from __future__ import annotations

import argparse
import json
import os
# The audit runner passes a fixed argv list to a local Python module.
import subprocess  # nosec B404
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional, Sequence


# This is a public outcome label, never a credential.
PASS = "PASS"  # nosec B105
VULNERABILITY_FOUND = "VULNERABILITY_FOUND"
SCANNER_ERROR = "SCANNER_ERROR"


def _load_audit_payload(path: Path) -> Dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"pip-audit did not produce valid JSON: {exc}") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("dependencies"), list):
        raise ValueError("pip-audit JSON is missing its dependencies list")
    return payload


def _vulnerability_count(payload: Dict[str, Any]) -> int:
    return sum(
        len(dependency.get("vulns", []))
        for dependency in payload["dependencies"]
        if isinstance(dependency, dict) and isinstance(dependency.get("vulns", []), list)
    )


def classify_result(
    returncode: int,
    payload: Optional[Dict[str, Any]],
    error: Optional[str] = None,
) -> Dict[str, Any]:
    """Classify a pip-audit execution without treating scanner errors as pass."""
    if error is not None or payload is None:
        return {
            "status": SCANNER_ERROR,
            "scanner_exit_code": returncode,
            "vulnerability_count": None,
            "error": error or "pip-audit produced no report",
        }

    vulnerabilities = _vulnerability_count(payload)
    if vulnerabilities:
        return {
            "status": VULNERABILITY_FOUND,
            "scanner_exit_code": returncode,
            "vulnerability_count": vulnerabilities,
            "error": None,
        }
    if returncode == 0:
        return {
            "status": PASS,
            "scanner_exit_code": returncode,
            "vulnerability_count": 0,
            "error": None,
        }
    return {
        "status": SCANNER_ERROR,
        "scanner_exit_code": returncode,
        "vulnerability_count": 0,
        "error": "pip-audit returned a non-zero exit code without vulnerability data",
    }


def _atomic_json_write(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.stem}-", suffix=".json", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink()


def run_audit(
    requirements: Path,
    report_path: Path,
    executable: str = sys.executable,
    runner=subprocess.run,
) -> Dict[str, Any]:
    """Run pip-audit and persist a report for PASS, vulnerability and tool error."""
    if not requirements.is_file():
        result = classify_result(2, None, f"Requirements file does not exist: {requirements}")
        _atomic_json_write(report_path, {**result, "audit": None})
        return result

    raw_report = report_path.with_name(f".{report_path.stem}.raw.json")
    try:
        completed = runner(
            [
                executable,
                "-m",
                "pip_audit",
                "-r",
                str(requirements),
                "--format",
                "json",
                "--output",
                str(raw_report),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        try:
            payload = _load_audit_payload(raw_report)
            result = classify_result(completed.returncode, payload)
        except ValueError as exc:
            result = classify_result(completed.returncode, None, str(exc))
            payload = None
        if result["status"] == SCANNER_ERROR and completed.stderr.strip():
            result["error"] = f"{result['error']}: {completed.stderr.strip()[:1000]}"
        _atomic_json_write(report_path, {**result, "audit": payload})
        return result
    except OSError as exc:
        result = classify_result(2, None, f"Could not execute pip-audit: {exc}")
        _atomic_json_write(report_path, {**result, "audit": None})
        return result
    finally:
        raw_report.unlink(missing_ok=True)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--requirements", default="requirements.txt")
    parser.add_argument("--report", required=True)
    args = parser.parse_args(argv)

    result = run_audit(Path(args.requirements), Path(args.report))
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["status"] == PASS else 1


if __name__ == "__main__":
    raise SystemExit(main())
