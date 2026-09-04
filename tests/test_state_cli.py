"""End-to-end coverage for the typed Phase 16 state CLI surface."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

specification = importlib.util.spec_from_file_location("phase16_state_cli", SCRIPTS / "state.py")
state_cli = importlib.util.module_from_spec(specification)
assert specification.loader is not None
specification.loader.exec_module(state_cli)

from memory_store import MemoryStore  # noqa: E402
from project_registry import ProjectRegistry  # noqa: E402


def _invoke(capsys, vault: Path, *arguments: str) -> tuple[int, dict]:
    exit_code = state_cli.main(["--vault", str(vault), "--json", *arguments])
    return exit_code, json.loads(capsys.readouterr().out)


def test_typed_cli_drives_each_state_lifecycle_without_a_generic_patch(capsys, tmp_path):
    ProjectRegistry(tmp_path).register(tmp_path / "brain-eleven", project_id="brain-eleven")
    source = ("--source", "user", "--source-reference", "cli-test")

    code, initialized = _invoke(capsys, tmp_path, "init", "--project-id", "brain-eleven", *source)
    assert code == 0
    assert initialized["revision"] == 1

    code, phase = _invoke(
        capsys, tmp_path, "set-phase", "--project-id", "brain-eleven", "--phase-id", "phase-16",
        "--title", "Task + State Model", "--record-id", "mil_cli", "--expected-revision", "1", *source,
    )
    assert code == 0
    assert phase["revision"] == 2
    assert phase["current"]["milestone"]["phase_id"] == "phase-16"

    code, completed = _invoke(
        capsys, tmp_path, "transition-phase", "--project-id", "brain-eleven", "--milestone-id", "mil_cli",
        "--target-status", "COMPLETED", "--expected-revision", "2", *source,
    )
    assert code == 0
    assert completed["current"]["milestone"]["status"] == "COMPLETED"

    operations = (
        ("set-objective", ("--text", "Finish the state CLI", "--record-id", "obj_cli")),
        ("add-requirement", ("--text", "No generic patch", "--record-id", "req_cli")),
        ("resolve-requirement", ("--requirement-id", "req_cli")),
        ("add-work-item", ("--text", "Exercise typed CLI", "--record-id", "wrk_cli")),
        ("transition-work-item", ("--work-item-id", "wrk_cli", "--target-status", "DONE")),
        ("add-blocker", ("--text", "Synthetic blocker", "--severity", "HIGH", "--record-id", "blk_cli")),
        ("resolve-blocker", ("--blocker-id", "blk_cli")),
        ("add-constraint", ("--text", "offline_only", "--record-id", "con_cli")),
        ("add-risk", ("--text", "Synthetic risk", "--severity", "MEDIUM", "--record-id", "rsk_cli")),
    )
    revision = 3
    for command, command_arguments in operations:
        code, result = _invoke(
            capsys,
            tmp_path,
            command,
            "--project-id",
            "brain-eleven",
            *command_arguments,
            "--expected-revision",
            str(revision),
            *source,
        )
        assert code == 0
        revision += 1
        assert result["revision"] == revision

    MemoryStore(tmp_path).append({
        "memory_id": "mem_cli_global",
        "content": "Global memory for CLI reference.",
        "type": "decision",
        "status": "active",
        "scope": "global",
    })
    code, referenced = _invoke(
        capsys, tmp_path, "add-memory-reference", "--project-id", "brain-eleven",
        "--memory-id", "mem_cli_global", "--expected-revision", str(revision), *source,
    )
    assert code == 0
    assert referenced["revision"] == revision + 1

    code, shown = _invoke(capsys, tmp_path, "show", "--project-id", "brain-eleven")
    assert code == 0
    assert shown["status"] == "AVAILABLE"
    assert shown["state_revision"] == revision + 1
    assert len(shown["constraints"]) == 1
    assert len(shown["risks"]) == 1
    assert shown["references"]["valid"] == ["mem_cli_global"]


def test_cli_returns_a_stable_machine_error_for_a_stale_state_revision(capsys, tmp_path):
    ProjectRegistry(tmp_path).register(tmp_path / "brain-eleven", project_id="brain-eleven")
    _invoke(capsys, tmp_path, "init", "--project-id", "brain-eleven")

    code, error = _invoke(
        capsys, tmp_path, "set-objective", "--project-id", "brain-eleven", "--text", "stale",
        "--record-id", "obj_stale", "--expected-revision", "0",
    )

    assert code == 2
    assert error["error"]["code"] == "STATE_CONFLICT"
