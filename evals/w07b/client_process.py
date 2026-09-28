"""Safe subprocess setup for isolated native-client evidence runs.

Set ``W07B_CLAUDE_CONFIG_DIR`` to reuse one disposable profile for interactive
sign-in and evidence runs. The helper accepts it only under system temp; when
unset, it uses the caller's per-run temporary profile.
"""
from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path


def claude_environment(config_dir: Path) -> dict[str, str]:
    """Keep Claude settings, session history and plugins in the test profile."""
    env = os.environ.copy()
    override = env.get("W07B_CLAUDE_CONFIG_DIR")
    selected = Path(override).resolve() if override else Path(config_dir).resolve()
    temp_root = Path(tempfile.gettempdir()).resolve()
    default_profile = (Path.home() / ".claude").resolve()
    try:
        common = os.path.commonpath((str(selected), str(temp_root)))
    except ValueError as exc:
        raise RuntimeError("CLAUDE_CONFIG_NOT_ISOLATED") from exc
    if (os.path.normcase(common) != os.path.normcase(str(temp_root))
            or os.path.normcase(str(selected)) == os.path.normcase(str(default_profile))):
        raise RuntimeError("CLAUDE_CONFIG_NOT_ISOLATED")
    selected.mkdir(parents=True, exist_ok=True)
    env["CLAUDE_CONFIG_DIR"] = str(selected)
    env.pop("W07B_CLAUDE_CONFIG_DIR", None)
    return env


def run_claude(cwd: Path, settings_path: Path, prompt: str, *,
               session_id: str | None = None, timeout: int = 120) -> subprocess.CompletedProcess[str]:
    """Run Claude with isolated settings and session-history storage."""
    cmd = ["claude", "-p", prompt, "--settings", str(settings_path), "--setting-sources", "",
           "--strict-mcp-config", "--tools", "", "--output-format", "json"]
    if session_id:
        cmd += ["--resume", session_id]
    return subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True,
                          encoding="utf-8", timeout=timeout,
                          env=claude_environment(settings_path.parent))
