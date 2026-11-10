import pytest

from brain_eleven.memory import MemoryStore
from brain_eleven.projects.registry import ProjectRegistry
from brain_eleven.runtime.context import _inputs_current
from brain_eleven.state import StateService
from brain_eleven.state.resolver import StateResolver


@pytest.fixture
def revisions(tmp_path):
    vault = tmp_path / 'vault'
    vault.mkdir()
    project_id = ProjectRegistry(vault).register(vault)['project_id']
    StateService(vault).init_project(project_id, source={'type': 'user', 'reference': 'test'})
    state = StateResolver(vault).resolve(project_id)
    current = {
        'memory': MemoryStore(vault).revision(),
        'state': {project_id: {'status': state.status, 'revision': state.state_revision}},
        'registry': ProjectRegistry(vault).load()['revision'],
    }
    return vault, project_id, current


def test_current_inputs_are_current(revisions):
    vault, _, current = revisions
    assert _inputs_current(vault, current) is True


def test_changed_memory_revision_is_stale(revisions):
    vault, _, current = revisions
    assert _inputs_current(vault, {**current, 'memory': current['memory'] + 1}) is False


def test_changed_state_revision_is_stale(revisions):
    vault, project_id, current = revisions
    state = {project_id: {**current['state'][project_id], 'revision': current['state'][project_id]['revision'] + 1}}
    assert _inputs_current(vault, {**current, 'state': state}) is False


def test_changed_registry_revision_is_stale(revisions):
    vault, _, current = revisions
    assert _inputs_current(vault, {**current, 'registry': current['registry'] + 1}) is False
