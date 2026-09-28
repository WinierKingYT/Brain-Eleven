"""Safe subprocess setup for isolated native-client evidence runs."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path


def claude_environment(config_dir: Path) -> dict[str, str]:
    """Keep Claude settings, session history and plugins in the test profile."""
    env = os.environ.copy()
    env["CLAUDE_CONFIG_DIR"] = str(Path(config_dir).resolve())
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
