"""TSC-03 strict serialized TaskStateContext decoding evidence."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest

from authority.serialization import task_state_from_dict
from authority import __main__ as authority_cli
from brain_eleven.runtime import task_state_context as task_state_module
from context_compiler_v2 import __main__ as compiler_cli
from project_registry import ProjectRegistry
from state_store import StateService


SOURCE = {"type": "user", "reference": "tsc-03-test"}
STAMP = "2026-09-23T10:00:00+03:00"


def _payload(tmp_path: Path) -> dict:
    tmp_path.mkdir(parents=True, exist_ok=True)
    project = tmp_path / "project"
    project.mkdir()
    ProjectRegistry(tmp_path).register(project, project_id="project-a")
    StateService(tmp_path).init_project("project-a", source=SOURCE, now=STAMP)
    return task_state_module.TaskStateComposer(tmp_path, project).compose("Keep this request private.").to_dict()


def _record(prefix: str, *, status: str = "ACTIVE", text_field: str = "text", **extra) -> dict:
    return {
        "id": f"{prefix}01",
        text_field: "private fact",
        "status": status,
        "source": dict(SOURCE),
        "created_at": STAMP,
        "updated_at": STAMP,
        **extra,
    }


def _rich_payload(tmp_path: Path) -> dict:
    payload = _payload(tmp_path)
    state = payload["state"]
    state["current"] = {
        "phase_id": "phase-1",
        "milestone": _record("mil_", status="ACTIVE", text_field="title", phase_id="phase-1"),
        "objective": _record("obj_"),
    }
    state["active_requirements"] = [_record("req_")]
    state["active_work_items"] = [_record("wrk_", status="TODO")]
    state["active_blockers"] = [_record("blk_", severity="HIGH", memory_ref="mem_01")]
    state["constraints"] = [_record("con_")]
    state["risks"] = [_record("rsk_", severity="LOW")]
    state["references"] = {
        "status": "checked", "valid": ["mem_01"], "dangling": [], "wrong_project": [],
    }
    return payload


def test_valid_rich_projection_round_trips_exactly(tmp_path):
    payload = _rich_payload(tmp_path)
    assert task_state_from_dict(payload).to_dict() == payload


def test_valid_unavailable_reference_health_preserves_bounded_error(tmp_path):
    payload = _payload(tmp_path)
    payload["state"]["references"] = {
        "status": "unavailable",
        "valid": [],
        "dangling": [],
        "wrong_project": [],
        "error": "memory authority unavailable",
    }
    assert task_state_from_dict(payload).to_dict() == payload


def test_real_archived_projection_round_trips(tmp_path):
    _payload(tmp_path)
    ProjectRegistry(tmp_path).set_status("project-a", "archived")
    archived = task_state_module.TaskStateComposer(tmp_path, tmp_path / "project").compose("Review state.").to_dict()
    assert archived["state"]["status"] == "PROJECT_ARCHIVED"
    assert task_state_from_dict(archived).to_dict() == archived


@pytest.mark.parametrize(
    ("path", "value", "message"),
    [
        (("status",), "invented", "state.status"),
        (("updated_at",), "2026-09-23", "updated_at"),
        (("archived",), "false", "archived"),
        (("freshness", "status"), "fresh", "freshness.status"),
        (("freshness", "age_days"), True, "freshness.age_days"),
        (("current", "phase_id"), 7, "current.phase_id"),
        (("references", "valid"), "mem_01", "references.valid"),
        (("references", "status"), "unchecked", "references.status"),
    ],
)
def test_nested_scalar_and_container_failures_are_rejected(tmp_path, path, value, message):
    payload = _payload(tmp_path)
    target = payload["state"]
    for part in path[:-1]:
        target = target[part]
    target[path[-1]] = value
    with pytest.raises(ValueError, match=message):
        task_state_from_dict(payload)


@pytest.mark.parametrize(
    ("mutator", "message"),
    [
        (lambda p: p["state"]["active_requirements"][0].update(id="bad"), "requirements.*id"),
        (lambda p: p["state"]["active_requirements"][0].update(status="RESOLVED"), "requirements.*status"),
        (lambda p: p["state"]["active_requirements"][0].update(content="not allowed"), "requirements.*fields"),
        (lambda p: p["state"]["active_requirements"][0]["source"].update(type="ai_proposed"), "source.type"),
        (lambda p: p["state"]["active_requirements"][0].update(created_at="2026-09-23"), "created_at"),
        (lambda p: p["state"]["active_blockers"][0].update(severity="URGENT"), "severity"),
        (lambda p: p["state"]["active_blockers"][0].update(memory_ref="wrong"), "memory_ref"),
        (lambda p: p["state"]["active_requirements"].append(deepcopy(p["state"]["active_requirements"][0])), "duplicate IDs"),
    ],
)
def test_malformed_records_are_rejected(tmp_path, mutator, message):
    payload = _rich_payload(tmp_path)
    mutator(payload)
    with pytest.raises(ValueError, match=message):
        task_state_from_dict(payload)


def test_reference_rules_reject_duplicates_and_status_error_mismatch(tmp_path):
    payload = _payload(tmp_path)
    payload["state"]["references"] = {
        "status": "checked", "valid": ["mem_x", "mem_x"], "dangling": [], "wrong_project": [],
    }
    with pytest.raises(ValueError, match="duplicate IDs"):
        task_state_from_dict(payload)

    payload = _payload(tmp_path / "second")
    payload["state"]["references"]["error"] = "must not be accepted"
    with pytest.raises(ValueError, match="error is not allowed"):
        task_state_from_dict(payload)


def test_error_state_requires_exact_empty_projection(tmp_path):
    unknown_root = tmp_path / "unknown"
    payload = task_state_module.TaskStateComposer(tmp_path, unknown_root).compose("Explain state.").to_dict()
    assert task_state_from_dict(payload).to_dict() == payload

    payload["state"]["active_work_items"] = [_record("wrk_", status="TODO")]
    with pytest.raises(ValueError, match="empty error projection"):
        task_state_from_dict(payload)


def test_diagnostics_do_not_echo_payload_values(tmp_path):
    payload = _rich_payload(tmp_path)
    sentinel = "password=DO_NOT_ECHO_THIS"
    payload["state"]["active_requirements"][0]["text"] = sentinel
    with pytest.raises(ValueError) as caught:
        task_state_from_dict(payload)
    message = str(caught.value)
    assert "active_requirements[0].text" in message
    assert sentinel not in message
    assert str(tmp_path) not in message


def test_cli_adapters_map_nested_rejection_to_invalid_input(tmp_path, capsys):
    payload = _payload(tmp_path)
    payload["state"]["freshness"]["status"] = "invalid"
    task_file = tmp_path / "task.json"
    task_file.write_text(json.dumps(payload), encoding="utf-8")
    authority_args = SimpleNamespace(task_state=task_file, router_result=tmp_path / "unused.json")
    assert authority_cli._resolve(authority_args) == 2
    assert json.loads(capsys.readouterr().out)["error"]["code"] == "INVALID_INPUT"

    request_file = tmp_path / "request.json"
    request_file.write_text(json.dumps({
        "schema_version": 1,
        "task_state": payload,
        "resolution_result": {},
        "budget": {"max_context_tokens": 1000},
    }), encoding="utf-8")
    compiler_args = SimpleNamespace(request_file=request_file, vault=tmp_path, mode="shadow", allow_history=False)
    assert compiler_cli._compile(compiler_args) == 2
    assert json.loads(capsys.readouterr().out)["error"]["code"] == "INVALID_INPUT"


def test_decoding_valid_and_invalid_payloads_never_writes_authority_files(tmp_path):
    payload = _payload(tmp_path)

    def snapshot() -> dict[str, bytes]:
        return {
            path.relative_to(tmp_path).as_posix(): path.read_bytes()
            for path in tmp_path.rglob("*")
            if path.is_file()
        }

    before = snapshot()
    task_state_from_dict(payload)
    malformed = deepcopy(payload)
    malformed["state"]["active_work_items"] = [{"text": "private state"}]
    with pytest.raises(ValueError):
        task_state_from_dict(malformed)
    assert snapshot() == before
