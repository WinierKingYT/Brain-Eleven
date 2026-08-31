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


def _backup_settings(settings_path: Path) -> Path:
    stamp = datetime.now().strftime("%Y%m%d%H%M%S%f")
    backup = settings_path.with_name(f"settings.json.brain-eleven.{stamp}.bak")
    shutil.copy2(settings_path, backup)
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


def _managed_settings_entries() -> List[tuple]:
    return [
        ("SessionStart", "bash ~/.claude/hooks/brain-eleven-session-start"),
        ("SessionEnd", "bash ~/.claude/hooks/brain-eleven-remember-opt-in"),
    ]


def install(home: Path, vault: Path, dry_run: bool = False) -> Dict:
    claude_dir = home / ".claude"
    settings_path = claude_dir / "settings.json"
    manifest_path = claude_dir / MANIFEST_NAME
    file_specs = {
        claude_dir / "commands" / "remember.md": TEMPLATE_ROOT / "commands" / "remember.md",
        claude_dir / "hooks" / "brain-eleven-session-start": TEMPLATE_ROOT / "hooks" / "brain-eleven-session-start",
        claude_dir / "hooks" / "brain-eleven-remember-opt-in": TEMPLATE_ROOT / "hooks" / "brain-eleven-remember-opt-in",
    }
    result = {"status": "dry_run" if dry_run else "installed", "files": [], "settings_changed": False}

    rendered = {str(path): _render(template, vault) for path, template in file_specs.items()}
    for path_text, content in rendered.items():
        path = Path(path_text)
        if path.exists():
            current = path.read_text(encoding="utf-8")
            if current != content:
                result["files"].append({"path": path_text, "status": "conflict"})
                continue
            result["files"].append({"path": path_text, "status": "unchanged", "sha256": _sha256_text(content)})
        else:
            result["files"].append({"path": path_text, "status": "create", "sha256": _sha256_text(content)})
            if not dry_run:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8", newline="\n")
                if path.name != "remember.md":
                    try:
                        path.chmod(path.stat().st_mode | 0o111)
                    except OSError:
                        pass

    settings = {}
    if settings_path.exists():
        settings = json.loads(settings_path.read_text(encoding="utf-8"))
    settings.setdefault("hooks", {})
    commands = set()
    settings_changed = False
    for event, command in _managed_settings_entries():
        commands.add(command)
        groups = settings["hooks"].setdefault(event, [])
        already_present = any(
            existing_event == event and hook.get("command") == command
            for existing_event, _group, hook in _iter_hook_commands(settings)
        )
        if not already_present:
            groups.append({"matcher": "*", "hooks": [{"type": "command", "command": command}]})
            settings_changed = True

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
