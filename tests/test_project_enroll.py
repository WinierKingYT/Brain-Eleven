"""Enroll a project folder for capture (owner request 2026-10-06)."""

from brain_eleven.__main__ import main
from brain_eleven.projects.registry import ProjectRegistry
from brain_eleven.runtime.storage import RuntimeConfig
from brain_eleven.state import StateStore
from tests.test_memclaim01_claim_key import _runtime


def test_project_add_registers_scopes_and_initialises_state(tmp_path):
    vault, _ = _runtime(tmp_path, shadow_accept=True)
    root = tmp_path / 'robloxdevOs'
    root.mkdir()

    assert main(['--vault', str(vault), 'project', 'add', str(root), '--label', 'robloxdevos']) == 0
    project = ProjectRegistry(vault).resolve(root)
    assert project['project_label'] == 'robloxdevos' and project['proactive_capture'] is True
    assert project['project_id'] in RuntimeConfig(vault).load()['project_ids']
    assert StateStore(vault).project_revision(project['project_id']) is not None

    # Repeating it changes nothing.
    again = RuntimeConfig(vault).enroll_project(root)
    assert again['project_id'] == project['project_id']
    assert RuntimeConfig(vault).load()['project_ids'].count(project['project_id']) == 1


def test_project_add_rejects_a_missing_folder(tmp_path):
    vault, _ = _runtime(tmp_path, shadow_accept=True)
    assert main(['--vault', str(vault), 'project', 'add', str(tmp_path / 'nope')]) == 2
