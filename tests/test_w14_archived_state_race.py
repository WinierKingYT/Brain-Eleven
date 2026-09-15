"""W-14 regression tests for registry/archive and state mutation ordering."""

import threading

import pytest

from brain_eleven.projects.registry import ProjectRegistry
from brain_eleven.state import StateProjectArchived, StateService


SOURCE = {"type": "user", "reference": "w14-test"}


def _setup(tmp_path):
    vault = tmp_path / "vault"
    root = tmp_path / "project"
    vault.joinpath(".claude").mkdir(parents=True)
    root.mkdir()
    registry = ProjectRegistry(vault)
    registry.register(root, project_id="project-id")
    service = StateService(vault)
    service.init_project("project-id", source=SOURCE, now="2026-01-01T00:00:00Z")
    return vault, service


def test_archive_first_rejects_without_state_effect(tmp_path):
    vault, service = _setup(tmp_path)
    ProjectRegistry(vault).set_status("project-id", "archived")
    before = service.store.get_project("project-id")

    with pytest.raises(StateProjectArchived):
        service.add_requirement(
            "project-id",
            text="must not be written",
            expected_revision=before["revision"],
            source=SOURCE,
        )

    after = service.store.get_project("project-id")
    assert after == before


def test_mutation_first_holds_registry_lock_until_state_commit(tmp_path):
    vault, service = _setup(tmp_path)
    checked = threading.Event()
    release = threading.Event()
    archive_started = threading.Event()
    archive_done = threading.Event()
    errors = []

    original_check = service._require_active_project

    def gated_check(project_id):
        result = original_check(project_id)
        checked.set()
        assert release.wait(5)
        return result

    service._require_active_project = gated_check

    def mutate():
        try:
            service.add_requirement(
                "project-id",
                text="serialized mutation",
                expected_revision=1,
                source=SOURCE,
            )
        except BaseException as exc:
            errors.append(exc)

    def archive():
        archive_started.set()
        try:
            ProjectRegistry(vault).set_status("project-id", "archived")
        except BaseException as exc:
            errors.append(exc)
        finally:
            archive_done.set()

    mutation_thread = threading.Thread(target=mutate)
    mutation_thread.start()
    assert checked.wait(5)

    archive_thread = threading.Thread(target=archive)
    archive_thread.start()
    assert archive_started.wait(5)
    assert not archive_done.wait(0.25), "archive bypassed the lifecycle boundary"

    release.set()
    mutation_thread.join(5)
    archive_thread.join(5)

    assert errors == []
    assert not mutation_thread.is_alive()
    assert not archive_thread.is_alive()
    assert archive_done.is_set()
    assert ProjectRegistry(vault).get("project-id")["status"] == "archived"
    assert service.store.get_project("project-id")["revision"] == 2
    assert service.store.get_project("project-id")["requirements"][0]["text"] == "serialized mutation"

