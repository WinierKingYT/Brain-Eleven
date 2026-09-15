"""W-17 fail-closed containment tests for vault-owned runtime state."""

import os
from pathlib import Path
import subprocess

import pytest

from brain_eleven.runtime import storage
from brain_eleven.runtime.path_safety import RuntimePathError, assert_runtime_snapshot, guard_runtime_path


def _make_link(link: Path, target: Path, *, directory: bool = True):
    try:
        link.symlink_to(target, target_is_directory=directory)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"symlink unavailable: {exc}")


def _vault(tmp_path: Path) -> Path:
    vault = tmp_path / "vault"
    vault.mkdir()
    return vault


def test_runtime_directory_symlink_rejected_before_external_effect(tmp_path):
    vault = _vault(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    (vault / ".brain-eleven").mkdir()
    _make_link(vault / ".brain-eleven" / "runtime", outside)

    with pytest.raises(RuntimePathError):
        storage.RuntimeConfig(vault).set_human_approval(True)

    assert list(outside.iterdir()) == []
    assert not (outside / "config.json.lock").exists()
    assert not (outside / "config.json").exists()


def test_brain_eleven_ancestor_symlink_rejected_before_external_effect(tmp_path):
    vault = _vault(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    _make_link(vault / ".brain-eleven", outside)

    with pytest.raises(RuntimePathError):
        storage.RuntimeConfig(vault).set_human_approval(True)

    assert list(outside.iterdir()) == []


def test_final_config_symlink_is_rejected_and_target_is_unchanged(tmp_path):
    vault = _vault(tmp_path)
    cfg = storage.RuntimeConfig(vault)
    cfg.ensure_root()
    outside = tmp_path / "outside-config.json"
    outside.write_text('{"sentinel":true}', encoding="utf-8")
    cfg.path.symlink_to(outside)

    with pytest.raises(RuntimePathError):
        cfg.set_human_approval(True)

    assert outside.read_text(encoding="utf-8") == '{"sentinel":true}'
    assert cfg.path.is_symlink()


def test_runtime_escape_is_rejected_without_writing_outside_root(tmp_path):
    vault = _vault(tmp_path)
    cfg = storage.RuntimeConfig(vault)
    target = cfg.root / ".." / "escaped.json"

    with pytest.raises(RuntimePathError):
        storage.write_json(target, {"outside": True})

    assert not (vault / ".brain-eleven" / "escaped.json").exists()
    assert not (tmp_path / "escaped.json").exists()


def test_missing_regular_runtime_directories_are_created_and_written(tmp_path):
    vault = _vault(tmp_path)
    cfg = storage.RuntimeConfig(vault)

    cfg.set_human_approval(True)

    assert cfg.root.is_dir()
    assert cfg.load()["b1_human_approval"] is True


def test_nested_missing_vault_parents_preserve_recursive_mkdir_behavior(tmp_path):
    vault = tmp_path / "missing" / "nested" / "vault"
    cfg = storage.RuntimeConfig(vault)

    cfg.set_human_approval(True)

    assert cfg.root.is_dir()
    assert cfg.load()["b1_human_approval"] is True


def test_regular_runtime_write_keeps_atomic_json_behavior(tmp_path):
    vault = _vault(tmp_path)
    cfg = storage.RuntimeConfig(vault)
    target = cfg.root / "artifacts" / "report.json"

    storage.write_json(target, {"z": 1, "a": "ok"})

    assert storage.read_json(target) == {"a": "ok", "z": 1}
    assert not list(target.parent.glob(".*report.json"))


def test_path_swap_between_temp_creation_and_publish_fails_closed(tmp_path, monkeypatch):
    vault = _vault(tmp_path)
    cfg = storage.RuntimeConfig(vault)
    target = cfg.root / "artifacts" / "report.json"
    outside = tmp_path / "outside"
    outside.mkdir()
    original_check = storage.assert_runtime_snapshot

    def swap_then_check(root, path, snapshot):
        parent = Path(path).parent
        moved = tmp_path / "moved-artifacts"
        parent.rename(moved)
        _make_link(parent, outside)
        return original_check(root, path, snapshot)

    monkeypatch.setattr(storage, "assert_runtime_snapshot", swap_then_check)
    with pytest.raises(RuntimePathError):
        storage.write_json(target, {"must": "stay inside"})

    assert list(outside.iterdir()) == []
    assert not (outside / "report.json").exists()
    assert not target.exists()


@pytest.mark.skipif(os.name != "nt", reason="Windows junction/reparse evidence")
def test_windows_junction_is_rejected_even_when_not_a_symlink(tmp_path):
    vault = _vault(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    brain = vault / ".brain-eleven"
    brain.mkdir()
    runtime = brain / "runtime"
    completed = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(runtime), str(outside)],
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0 or not runtime.exists():
        pytest.skip("junction creation unavailable")
    assert not runtime.is_symlink()

    with pytest.raises(RuntimePathError):
        storage.RuntimeConfig(vault).set_human_approval(True)

    assert list(outside.iterdir()) == []


def test_snapshot_detects_replaced_runtime_parent(tmp_path):
    vault = _vault(tmp_path)
    cfg = storage.RuntimeConfig(vault)
    target = cfg.root / "artifacts" / "report.json"
    snapshot = guard_runtime_path(cfg.root, target)
    parent = target.parent
    moved = tmp_path / "moved-artifacts"
    parent.rename(moved)
    outside = tmp_path / "outside"
    outside.mkdir()
    _make_link(parent, outside)

    with pytest.raises(RuntimePathError):
        assert_runtime_snapshot(cfg.root, target, snapshot)
