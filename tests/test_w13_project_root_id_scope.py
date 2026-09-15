"""W-13 regression cases for project-root/project-ID consistency."""

import importlib.util
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from brain_eleven.memory.scope import resolve_capture_scope
from brain_eleven.projects.registry import ProjectRegistry

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"


def _registry(vault: Path, root: Path, project_id: str) -> None:
    ProjectRegistry(vault).register(root, project_id=project_id)


def test_mismatched_root_and_project_id_fails_closed_without_registry_write(tmp_path):
    vault = tmp_path / "vault"
    root_a = tmp_path / "project-a"
    root_b = tmp_path / "project-b"
    vault.joinpath(".claude").mkdir(parents=True)
    root_a.mkdir()
    root_b.mkdir()
    _registry(vault, root_a, "project-a-id")
    _registry(vault, root_b, "project-b-id")
    before = ProjectRegistry(vault).load()

    with pytest.raises(ValueError, match="PROJECT_ROOT_ID_MISMATCH"):
        resolve_capture_scope(
            scope="project",
            project_root=root_a,
            project_id="project-b-id",
            registry_path=vault / ".claude" / "project-registry.json",
        )

    after = ProjectRegistry(vault).load()
    assert after["revision"] == before["revision"]
    assert after["projects"] == before["projects"]


def test_matching_root_and_project_id_uses_registered_identity(tmp_path):
    vault = tmp_path / "vault"
    root = tmp_path / "project"
    vault.joinpath(".claude").mkdir(parents=True)
    root.mkdir()
    _registry(vault, root, "stable-project-id")

    assert resolve_capture_scope(
        scope="project",
        project_root=root,
        project_id="stable-project-id",
        registry_path=vault / ".claude" / "project-registry.json",
    ) == ("project", "project", "stable-project-id")


def test_unregistered_root_with_explicit_id_rejects_without_registration(tmp_path):
    vault = tmp_path / "vault"
    root = tmp_path / "unregistered"
    vault.joinpath(".claude").mkdir(parents=True)
    root.mkdir()
    registry_file = vault / ".claude" / "project-registry.json"

    with pytest.raises(ValueError, match="PROJECT_ROOT_ID_UNREGISTERED"):
        resolve_capture_scope(
            scope="project",
            project_root=root,
            project_id="caller-id",
            registry_path=registry_file,
        )

    assert not registry_file.exists()


def test_root_only_keeps_auto_registration_and_relocation_identity(tmp_path):
    vault = tmp_path / "vault"
    old_root = tmp_path / "old"
    new_root = tmp_path / "new"
    vault.joinpath(".claude").mkdir(parents=True)
    old_root.mkdir()
    new_root.mkdir()

    first = resolve_capture_scope(
        scope="project",
        project_root=old_root,
        registry_path=vault / ".claude" / "project-registry.json",
    )
    ProjectRegistry(vault).relocate(first[2], new_root)
    second = resolve_capture_scope(
        scope="project",
        project_root=new_root,
        registry_path=vault / ".claude" / "project-registry.json",
    )
    assert second[2] == first[2]


def test_global_scope_rejects_project_metadata_but_keeps_root_only_cli_behavior(tmp_path):
    with pytest.raises(ValueError, match="global memory"):
        resolve_capture_scope(scope="global", project_id="project-id")
    assert resolve_capture_scope(scope="global", project_root=tmp_path / "root") == (
        "global", "", ""
    )


def test_remember_rejects_mismatch_before_canonical_write(tmp_path):
    from brain_eleven.memory.capture import remember

    vault = tmp_path / "vault"
    root_a = tmp_path / "project-a"
    root_b = tmp_path / "project-b"
    vault.joinpath(".claude").mkdir(parents=True)
    root_a.mkdir()
    root_b.mkdir()
    _registry(vault, root_a, "project-a-id")
    _registry(vault, root_b, "project-b-id")

    with pytest.raises(ValueError, match="PROJECT_ROOT_ID_MISMATCH"):
        remember(
            type_="decision",
            content="This must not cross project scope",
            vault_path=vault,
            project_root=root_a,
            project_id="project-b-id",
        )

    assert not (vault / ".claude" / "validated-memory.json").exists()


def _load_search_api(vault: Path):
    os.environ["VAULT_PATH"] = str(vault)
    os.environ.pop("BRAIN_ELEVEN_API_KEY", None)
    name = f"w13_search_api_{id(vault)}"
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / "search-api.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.mark.integration
def test_search_api_rejects_mismatched_root_and_project_id(tmp_path):
    vault = tmp_path / "vault"
    root_a = tmp_path / "project-a"
    root_b = tmp_path / "project-b"
    vault.joinpath(".claude").mkdir(parents=True)
    root_a.mkdir()
    root_b.mkdir()
    _registry(vault, root_a, "project-a-id")
    _registry(vault, root_b, "project-b-id")
    module = _load_search_api(vault)

    with TestClient(module.app) as client:
        response = client.post(
            "/memories",
            json={
                "type": "decision",
                "content": "API mismatch must be rejected",
                "scope": "project",
                "project_id": "project-b-id",
                "project_root": str(root_a),
            },
        )

    assert response.status_code == 422
    assert "PROJECT_ROOT_ID_MISMATCH" in response.json()["detail"]
    memory_file = vault / ".claude" / "validated-memory.json"
    assert not memory_file.exists() or "API mismatch must be rejected" not in memory_file.read_text(encoding="utf-8")

