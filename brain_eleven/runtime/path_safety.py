"""Fail-closed containment checks for vault-owned runtime paths.

Runtime state is operational data, but it is still written below a selected
vault.  This module deliberately has no storage or locking imports so it can
be used by both the JSON writer and the shared lock implementation without a
dependency cycle.
"""

from __future__ import annotations

import os
from pathlib import Path
import stat
from dataclasses import dataclass


class RuntimePathError(OSError):
    """Raised when a runtime path cannot be proven vault-owned."""


def _lexists(path: Path) -> bool:
    return os.path.lexists(os.fspath(path))


def _is_reparse_or_symlink(path: Path) -> bool:
    """Return whether *path* redirects through a link or reparse point."""
    info = os.lstat(path)
    if stat.S_ISLNK(info.st_mode):
        return True
    # FILE_ATTRIBUTE_REPARSE_POINT.  Path.is_symlink() is false for many
    # Windows junctions, so the attribute check is intentional.
    return bool(getattr(info, "st_file_attributes", 0) & 0x400)


def runtime_root_for_path(path: str | Path) -> Path | None:
    """Find the lexical ``.brain-eleven/runtime`` root containing *path*.

    Runtime paths are intentionally recognized lexically.  Resolving first
    would follow the very redirect that this policy must reject.
    """
    candidate = Path(path).absolute()
    for parent in (candidate, *candidate.parents):
        if parent.name == "runtime" and parent.parent.name == ".brain-eleven":
            return parent
    return None


def _identity(path: Path) -> tuple[int, int, int, int]:
    info = os.lstat(path)
    return (info.st_dev, info.st_ino, info.st_mode, getattr(info, "st_file_attributes", 0))


def _check_component(path: Path, *, directory: bool = False) -> None:
    if not _lexists(path):
        return
    if _is_reparse_or_symlink(path):
        raise RuntimePathError("Runtime path contains a link or reparse point")
    if directory and not stat.S_ISDIR(os.lstat(path).st_mode):
        raise RuntimePathError("Runtime path component is not a directory")


def _mkdir_checked(path: Path) -> None:
    path = Path(path).absolute()
    if _lexists(path):
        _check_component(path, directory=True)
        return
    parent = path.parent
    _check_existing_ancestors(parent)
    parent_identity = _identity(parent)
    created = False
    try:
        path.mkdir()
        created = True
    except FileExistsError:
        # A concurrent creator is acceptable only after it passes the same
        # no-follow check.  A link created during the race is rejected.
        pass
    try:
        # A selected vault/ancestor can be replaced while mkdir follows the
        # lexical parent.  Detect that swap before accepting the new
        # component, and remove a component created by this call so the race
        # cannot leave an outside directory behind.
        _check_existing_ancestors(parent)
        if _identity(parent) != parent_identity:
            raise RuntimePathError("Runtime parent changed during directory creation")
        _check_component(path, directory=True)
    except Exception:
        if created and _lexists(path):
            try:
                info = os.lstat(path)
                if stat.S_ISDIR(info.st_mode) and not _is_reparse_or_symlink(path):
                    path.rmdir()
            except OSError:
                pass
        raise


def _check_existing_ancestors(path: Path) -> None:
    """Reject links/reparse points anywhere above a selected path."""
    current = Path(path).absolute()
    while True:
        if _lexists(current):
            _check_component(current, directory=True)
        parent = current.parent
        if parent == current:
            break
        current = parent


def _ensure_directory_tree(path: Path) -> None:
    """Create a missing directory tree without following existing links."""
    path = Path(path).absolute()
    missing = []
    current = path
    while not _lexists(current):
        missing.append(current)
        parent = current.parent
        if parent == current:
            raise RuntimePathError("Runtime directory has no regular ancestor")
        current = parent
    _check_existing_ancestors(current)
    for component in reversed(missing):
        _mkdir_checked(component)


def _ensure_root(root: Path) -> None:
    """Create missing vault runtime directories one component at a time."""
    root = Path(root).absolute()
    if len(root.parents) < 2 or root.parent.name != ".brain-eleven":
        raise RuntimePathError("Invalid runtime root")
    vault = root.parent.parent
    # The selected vault is the containment anchor.  Existing symlink/reparse
    # vaults are rejected rather than silently resolving to another tree.
    _ensure_directory_tree(vault)
    _mkdir_checked(root.parent)
    _mkdir_checked(root)


def _existing_root_check(root: Path) -> None:
    """Validate existing root ancestors without creating missing paths."""
    root = Path(root).absolute()
    if len(root.parents) < 2 or root.parent.name != ".brain-eleven":
        raise RuntimePathError("Invalid runtime root")
    _check_existing_ancestors(root)


def validate_vault_path(vault: str | Path) -> Path:
    """Validate the selected vault lexically before any ``resolve()`` call."""
    candidate = Path(vault).expanduser()
    if not candidate.is_absolute():
        candidate = Path.cwd() / candidate
    _check_existing_ancestors(candidate)
    return candidate


def _relative(root: Path, target: Path) -> Path:
    root = Path(root).absolute()
    target = Path(target).absolute()
    try:
        return target.relative_to(root)
    except ValueError as exc:
        raise RuntimePathError("Runtime destination escapes its vault root") from exc


def _resolved_contained(root: Path, target: Path) -> None:
    """Check resolved containment after all existing components are checked."""
    if not _lexists(root):
        return
    try:
        resolved_root = root.resolve(strict=True)
        resolved_target = target.resolve(strict=False)
        resolved_target.relative_to(resolved_root)
    except (OSError, RuntimeError, ValueError) as exc:
        raise RuntimePathError("Runtime destination is outside its vault root") from exc


@dataclass(frozen=True)
class RuntimePathSnapshot:
    """Directory identities used to detect a path swap around publication."""

    root: tuple[int, int, int, int]
    parent: tuple[int, int, int, int]


def guard_runtime_path(root: str | Path, target: str | Path, *, create: bool = True) -> RuntimePathSnapshot:
    """Validate a runtime destination before locks, mkdir or temporary files.

    Missing runtime directories are created only after every existing
    component has passed lstat/reparse checks.  Existing final symlinks are
    rejected, so a config symlink is never followed or replaced implicitly.
    """
    root = Path(root).absolute()
    target = Path(target).absolute()
    relative = _relative(root, target)

    # Check before creation so a link at any existing ancestor cannot cause an
    # external side effect while this function prepares the path.
    _existing_root_check(root)
    if create:
        _ensure_root(root)
        current = root
        for part in relative.parts[:-1]:
            current = current / part
            _mkdir_checked(current)
    else:
        _existing_root_check(root)
        current = root
        for part in relative.parts[:-1]:
            current = current / part
            if _lexists(current):
                _check_component(current, directory=True)

    # A dangling symlink is also lexists=True and must be rejected.
    if _lexists(target):
        _check_component(target)
        if stat.S_ISDIR(os.lstat(target).st_mode):
            raise RuntimePathError("Runtime destination is a directory")
    _resolved_contained(root, target)
    if not _lexists(root) or not _lexists(target.parent):
        raise RuntimePathError("Runtime destination parent is unavailable")
    return RuntimePathSnapshot(_identity(root), _identity(target.parent))


def assert_runtime_snapshot(root: str | Path, target: str | Path, snapshot: RuntimePathSnapshot) -> None:
    """Revalidate components and identities immediately before publication."""
    current = guard_runtime_path(root, target, create=False)
    if current != snapshot:
        raise RuntimePathError("Runtime path changed during publication")


def ensure_runtime_directory(root: str | Path, directory: str | Path) -> Path:
    """Create and validate a runtime subdirectory before a caller enters it."""
    root = Path(root).absolute()
    target = Path(directory).absolute()
    relative = _relative(root, target)
    _existing_root_check(root)
    _ensure_root(root)
    current = root
    for part in relative.parts:
        current = current / part
        _mkdir_checked(current)
    _resolved_contained(root, target)
    return target


__all__ = [
    "RuntimePathError",
    "RuntimePathSnapshot",
    "assert_runtime_snapshot",
    "ensure_runtime_directory",
    "guard_runtime_path",
    "runtime_root_for_path",
    "validate_vault_path",
]
