#!/usr/bin/env python3
"""Install or remove Brain-Eleven's global Claude Code integration.

The installer is deliberately conservative: it creates only Brain-Eleven
owned files, adds only exact managed hook entries, preserves unrelated
settings, and refuses to overwrite a user-modified managed file. A manifest
records hashes so uninstall can remove only files that are still ours.
"""

import argparse
import hashlib
import json
import os
import shlex
import shutil
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List


REPO_ROOT = Path(__file__).resolve().parent.parent
TEMPLATE_ROOT = REPO_ROOT / "templates" / "claude"
LEGACY_TEMPLATE_ROOT = TEMPLATE_ROOT / "legacy"
MANIFEST_NAME = ".brain-eleven-install.json"


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _shell_path(path: Path) -> str:
    """Render a path safely for a bash assignment."""
    return shlex.quote(str(path).replace("\\", "/"))


def _render(template: Path, vault: Path) -> str:
    text = template.read_text(encoding="utf-8")
    return text.replace("{{VAULT_PATH}}", _shell_path(vault))


def _atomic_json_write(path: Path, data: Dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
        Path(tmp_name).replace(path)
    finally:
        tmp = Path(tmp_name)
        if tmp.exists():
            tmp.unlink()


def _atomic_text_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        Path(tmp_name).replace(path)
    finally:
        tmp = Path(tmp_name)
        if tmp.exists():
            tmp.unlink()


def _backup_settings(settings_path: Path) -> Path:
    stamp = datetime.now().strftime("%Y%m%d%H%M%S%f")
    backup = settings_path.with_name(f"settings.json.brain-eleven.{stamp}.bak")
    shutil.copy2(settings_path, backup)
    return backup


def _backup_managed_file(path: Path) -> Path:
    stamp = datetime.now().strftime("%Y%m%d%H%M%S%f")
    backup = path.with_name(f"{path.name}.brain-eleven.{stamp}.bak")
    shutil.copy2(path, backup)
    return backup


def _iter_hook_commands(settings: Dict) -> Iterable[tuple]:
    for event, groups in settings.get("hooks", {}).items():
        if not isinstance(groups, list):
            continue
        for group in groups:
            if not isinstance(group, dict):
                continue
            hooks = group.get("hooks", [])
            if not isinstance(hooks, list):
                continue
            for hook in hooks:
                if isinstance(hook, dict) and hook.get("type") == "command":
                    yield event, group, hook


def _remove_commands(settings: Dict, commands: set) -> bool:
    changed = False
    hooks = settings.get("hooks", {})
    for event, groups in list(hooks.items()):
        if not isinstance(groups, list):
            continue
        new_groups = []
        for group in groups:
            if not isinstance(group, dict):
                new_groups.append(group)
                continue
            group_hooks = group.get("hooks")
            if not isinstance(group_hooks, list):
                new_groups.append(group)
                continue
            remaining = [
                hook for hook in group_hooks
                if not (isinstance(hook, dict) and hook.get("type") == "command"
                        and hook.get("command") in commands)
            ]
            if len(remaining) != len(group_hooks):
                changed = True
            if remaining:
                updated = dict(group)
                updated["hooks"] = remaining
                new_groups.append(updated)
            else:
                changed = True
        hooks[event] = new_groups
    return changed


def _shell_hook_command(home: Path, hook_name: str) -> str:
    """Render a direct hook command without relying on ``~`` or nested shells.

    On Windows there is no single path form every bash accepts: Git Bash/MSYS
    (what Claude Code's own Bash tool uses, and the common case for a native
    Windows install) resolves a drive-letter path like ``C:/Users/...``
    directly, while WSL's bash only understands the ``/mnt/c/...`` mount
    form and cannot open ``C:/...`` at all - and there is no install-time
    signal that reliably predicts which bash will actually be invoked later,
    since that depends on how Claude Code itself is launched, not on
    ``os.name`` here. Emit both, right-to-left with a fallback: the first
    form that resolves runs the hook; if the leading form's path doesn't
    exist, bash exits before the hook body ever runs (`No such file or
    directory`, i.e. before any side effect), so the fallback is safe to
    attempt - at most one branch ever actually executes the hook.
    """
    hook_path = home / ".claude" / "hooks" / hook_name
    if os.name == "nt" and hook_path.drive:
        windows_path_text = str(hook_path).replace("\\", "/")
        drive = hook_path.drive.rstrip(":").lower()
        wsl_path_text = "/mnt/" + drive + "/" + "/".join(hook_path.parts[1:])
        return (
            f"bash {shlex.quote(windows_path_text)} "
            f"|| bash {shlex.quote(wsl_path_text)}"
        )
    hook_path_text = str(hook_path).replace("\\", "/")
    return f"bash {shlex.quote(hook_path_text)}"


def _managed_settings_entries(home: Path) -> List[tuple]:
    return [
        ("SessionStart", _shell_hook_command(home, "brain-eleven-session-start")),
        ("SessionEnd", _shell_hook_command(home, "brain-eleven-remember-opt-in")),
    ]


def _legacy_settings_commands() -> set:
    return {
        "bash ~/.claude/hooks/brain-eleven-session-start",
        "bash ~/.claude/hooks/brain-eleven-remember-opt-in",
    }


def _legacy_templates() -> Dict[str, Path]:
    """Known Brain-Eleven v1 artifacts eligible for a backup-first upgrade."""
    return {
        "commands/remember.md": LEGACY_TEMPLATE_ROOT / "remember-v1.md",
        "hooks/brain-eleven-remember-opt-in": LEGACY_TEMPLATE_ROOT / "brain-eleven-remember-opt-in-v1",
    }


def _managed_manifest_hashes(manifest_path: Path, vault: Path) -> Dict[str, str]:
    """Return trusted prior managed hashes for this exact vault, if available."""
    if not manifest_path.exists():
        return {}
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest_vault = Path(manifest.get("vault", "")).expanduser().resolve(strict=False)
        files = manifest.get("files", {})
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return {}
    if manifest_vault != vault.resolve(strict=False) or not isinstance(files, dict):
        return {}
    return {
        str(path): digest
        for path, digest in files.items()
        if isinstance(path, str) and isinstance(digest, str)
    }


def _managed_manifest_commands(manifest_path: Path, vault: Path) -> set:
    """Return trusted managed hook commands for this exact vault, if available."""
    if not manifest_path.exists():
        return set()
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest_vault = Path(manifest.get("vault", "")).expanduser().resolve(strict=False)
        commands = manifest.get("settings_commands", [])
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return set()
    if manifest_vault != vault.resolve(strict=False) or not isinstance(commands, list):
        return set()
    return {command for command in commands if isinstance(command, str)}


def install(home: Path, vault: Path, dry_run: bool = False) -> Dict:
    claude_dir = home / ".claude"
    settings_path = claude_dir / "settings.json"
    manifest_path = claude_dir / MANIFEST_NAME
    file_specs = {
        claude_dir / "commands" / "remember.md": TEMPLATE_ROOT / "commands" / "remember.md",
        claude_dir / "hooks" / "brain-eleven-session-start": TEMPLATE_ROOT / "hooks" / "brain-eleven-session-start",
        claude_dir / "hooks" / "brain-eleven-remember-opt-in": TEMPLATE_ROOT / "hooks" / "brain-eleven-remember-opt-in",
    }
    legacy_specs = _legacy_templates()
    prior_managed_hashes = _managed_manifest_hashes(manifest_path, vault)
    prior_managed_commands = _managed_manifest_commands(manifest_path, vault)
    result = {"status": "dry_run" if dry_run else "installed", "files": [], "settings_changed": False}

    rendered = {str(path): _render(template, vault) for path, template in file_specs.items()}
    for path_text, content in rendered.items():
        path = Path(path_text)
        if path.exists():
            current = path.read_text(encoding="utf-8")
            if current != content:
                relative = str(path.relative_to(claude_dir)).replace("\\", "/")
                legacy = legacy_specs.get(relative)
                is_prior_managed = prior_managed_hashes.get(path_text) == _sha256_text(current)
                if is_prior_managed or (legacy and current == _render(legacy, vault)):
                    result["files"].append({"path": path_text, "status": "upgrade"})
                else:
                    result["files"].append({"path": path_text, "status": "conflict"})
                continue
            result["files"].append({"path": path_text, "status": "unchanged", "sha256": _sha256_text(content)})
        else:
            result["files"].append({"path": path_text, "status": "create", "sha256": _sha256_text(content)})

    # A partially installed global integration is safer than overwriting a
    # user-owned command or hook. Preflight every managed file before writing
    # settings, a manifest, or any new files so a conflict is fail-closed.
    if any(item["status"] == "conflict" for item in result["files"]):
        result["status"] = "conflict"
        result["manifest"] = str(manifest_path)
        return result

    settings = {}
    if settings_path.exists():
        settings = json.loads(settings_path.read_text(encoding="utf-8"))
    settings.setdefault("hooks", {})
    commands = set()
    settings_changed = _remove_commands(
        settings,
        prior_managed_commands | _legacy_settings_commands(),
    )
    for event, command in _managed_settings_entries(home):
        commands.add(command)
        groups = settings["hooks"].setdefault(event, [])
        already_present = any(
            existing_event == event and hook.get("command") == command
            for existing_event, _group, hook in _iter_hook_commands(settings)
        )
        if not already_present:
            groups.append({"matcher": "*", "hooks": [{"type": "command", "command": command}]})
            settings_changed = True

    if not dry_run:
        for item in result["files"]:
            if item["status"] not in {"create", "upgrade"}:
                continue
            path = Path(item["path"])
            if item["status"] == "upgrade":
                item["backup"] = str(_backup_managed_file(path))
            _atomic_text_write(path, rendered[str(path)])
            if path.name != "remember.md":
                try:
                    path.chmod(path.stat().st_mode | 0o111)
                except OSError:
                    pass

    if settings_changed:
        result["settings_changed"] = True
        if not dry_run:
            claude_dir.mkdir(parents=True, exist_ok=True)
            backup = _backup_settings(settings_path) if settings_path.exists() else None
            _atomic_json_write(settings_path, settings)
            result["settings_backup"] = str(backup) if backup else None

    manifest = {
        "version": 1,
        "vault": str(vault),
        "files": {path: _sha256_text(content) for path, content in rendered.items()},
        "settings_commands": sorted(commands),
    }
    if not dry_run:
        _atomic_json_write(manifest_path, manifest)
    result["manifest"] = str(manifest_path)
    return result


def uninstall(home: Path, dry_run: bool = False) -> Dict:
    claude_dir = home / ".claude"
    manifest_path = claude_dir / MANIFEST_NAME
    if not manifest_path.exists():
        return {"status": "not_installed", "removed": [], "settings_changed": False}

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    result = {"status": "dry_run" if dry_run else "uninstalled", "removed": [], "skipped_modified": [], "settings_changed": False}
    for path_text, expected_hash in manifest.get("files", {}).items():
        path = Path(path_text)
        if not path.exists():
            continue
        current_hash = _sha256_text(path.read_text(encoding="utf-8"))
        if current_hash != expected_hash:
            result["skipped_modified"].append(path_text)
            continue
        result["removed"].append(path_text)
        if not dry_run:
            path.unlink()

    settings_path = claude_dir / "settings.json"
    if settings_path.exists():
        settings = json.loads(settings_path.read_text(encoding="utf-8"))
        changed = _remove_commands(settings, set(manifest.get("settings_commands", [])))
        if changed:
            result["settings_changed"] = True
            if not dry_run:
                backup = _backup_settings(settings_path)
                _atomic_json_write(settings_path, settings)
                result["settings_backup"] = str(backup)

    if not dry_run:
        manifest_path.unlink()
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Install Brain-Eleven global Claude Code integration")
    parser.add_argument("--vault", default=str(REPO_ROOT), help="Brain-Eleven repository/vault root")
    parser.add_argument("--home", default=str(Path.home()), help="Home directory containing .claude")
    parser.add_argument("--uninstall", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    home = Path(args.home).expanduser().resolve(strict=False)
    vault = Path(args.vault).expanduser().resolve(strict=False)
    result = uninstall(home, args.dry_run) if args.uninstall else install(home, vault, args.dry_run)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if not result.get("skipped_modified") and not any(
        item.get("status") == "conflict" for item in result.get("files", [])
    ) else 2


if __name__ == "__main__":
    raise SystemExit(main())
