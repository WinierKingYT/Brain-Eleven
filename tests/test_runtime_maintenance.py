"""IG-07 Slice 2A coverage for the packaged maintenance runtime."""

from __future__ import annotations

import ast
import importlib
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _write_vault(vault: Path) -> bytes:
    claude_dir = vault / ".claude"
    claude_dir.mkdir()
    payload = {
        "validated_memory": [
            {
                "memory_id": "maintenance-test-memory",
                "source_id": "daily:2026-09-11:observation:0:0",
                "type": "observation",
                "content": "Maintenance parity fixture",
                "confidence": 0.8,
                "timestamp": "2026-09-11T10:00:00",
                "quality_score": 0.8,
                "status": "active",
                "is_approved": True,
                "superseded_by": "",
            }
        ]
    }
    memory_file = claude_dir / "validated-memory.json"
    memory_file.write_text(json.dumps(payload), encoding="utf-8")
    return memory_file.read_bytes()


def _without_timestamp(value):
    if isinstance(value, dict):
        return {
            key: _without_timestamp(item)
            for key, item in value.items()
            if key != "generated_at"
        }
    if isinstance(value, list):
        return [_without_timestamp(item) for item in value]
    return value


def test_package_and_legacy_exports_preserve_object_identity() -> None:
    packaged = importlib.import_module("brain_eleven.runtime.maintenance")
    legacy = importlib.import_module("scripts.post_session_maintenance")
    bare = importlib.import_module("post_session_maintenance")

    for name in (
        "_run_step",
        "run_maintenance",
        "save_report",
        "summarize_for_shell",
        "main",
    ):
        assert getattr(legacy, name) is getattr(packaged, name)
        assert getattr(bare, name) is getattr(packaged, name)
    assert legacy.SURFACE_THRESHOLD is packaged.SURFACE_THRESHOLD
    assert legacy.logger is packaged.logger


def test_legacy_script_is_an_adapter_only() -> None:
    script = ROOT / "scripts" / "post_session_maintenance.py"
    tree = ast.parse(script.read_text(encoding="utf-8"))

    function_names = {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    assert function_names == {"_load_canonical"}
    assert not any(isinstance(node, ast.ClassDef) for node in ast.walk(tree))

    source = script.read_text(encoding="utf-8")
    assert "brain_eleven.runtime.maintenance" in source
    for implementation_name in (
        "def _run_step",
        "def run_maintenance",
        "def save_report",
        "def summarize_for_shell",
    ):
        assert implementation_name not in source


def test_package_and_legacy_reports_have_parity_without_memory_mutation(tmp_path: Path) -> None:
    packaged_vault = tmp_path / "packaged"
    legacy_vault = tmp_path / "legacy"
    packaged_vault.mkdir()
    legacy_vault.mkdir()
    packaged_memory = _write_vault(packaged_vault)
    legacy_memory = _write_vault(legacy_vault)

    packaged = importlib.import_module("brain_eleven.runtime.maintenance")
    legacy = importlib.import_module("scripts.post_session_maintenance")

    packaged_report = packaged.run_maintenance(str(packaged_vault), generated_by_run="parity")
    legacy_report = legacy.run_maintenance(str(legacy_vault), generated_by_run="parity")

    assert _without_timestamp(packaged_report) == _without_timestamp(legacy_report)
    assert (packaged_vault / ".claude" / "validated-memory.json").read_bytes() == packaged_memory
    assert (legacy_vault / ".claude" / "validated-memory.json").read_bytes() == legacy_memory

    packaged_path = packaged.save_report(packaged_report, str(packaged_vault))
    legacy_path = legacy.save_report(legacy_report, str(legacy_vault))
    assert _without_timestamp(json.loads(packaged_path.read_text(encoding="utf-8"))) == _without_timestamp(
        json.loads(legacy_path.read_text(encoding="utf-8"))
    )
    assert packaged.summarize_for_shell(packaged_report) == legacy.summarize_for_shell(legacy_report)


def test_legacy_cli_preserves_quiet_and_generated_by_run(tmp_path: Path) -> None:
    _write_vault(tmp_path)
    script = ROOT / "scripts" / "post_session_maintenance.py"
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)

    completed = subprocess.run(
        [
            sys.executable,
            str(script),
            "--vault",
            str(tmp_path),
            "--generated-by-run",
            "cli-parity",
            "--quiet",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        creationflags=creationflags,
        check=False,
    )

    assert completed.returncode == 0
    assert completed.stdout == ""
    report_path = tmp_path / ".claude" / "session-maintenance-report.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["generated_by_run"] == "cli-parity"
