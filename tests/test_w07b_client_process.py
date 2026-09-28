from __future__ import annotations

from pathlib import Path

from evals.w07b import client_process


def test_claude_subprocess_uses_isolated_config_and_history_dir(tmp_path: Path, monkeypatch):
    live_config = tmp_path / "live-profile"
    isolated_config = tmp_path / "isolated-profile"
    isolated_config.mkdir()
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(live_config))
    calls = []

    def fake_run(args, **kwargs):
        calls.append((args, kwargs))
        return "completed"

    monkeypatch.setattr(client_process.subprocess, "run", fake_run)
    result = client_process.run_claude(
        tmp_path, isolated_config / "isolated-settings.json", "synthetic decision",
        session_id="opaque-session", timeout=17,
    )

    assert result == "completed"
    args, kwargs = calls[0]
    assert args[-2:] == ["--resume", "opaque-session"]
    assert kwargs["env"]["CLAUDE_CONFIG_DIR"] == str(isolated_config.resolve())
    assert kwargs["env"]["CLAUDE_CONFIG_DIR"] != str(live_config)
    assert kwargs["timeout"] == 17
    assert kwargs["capture_output"] is True
    assert "CLAUDE_CONFIG_DIR" not in kwargs["env"] or kwargs["env"]["CLAUDE_CONFIG_DIR"] != str(live_config)
    assert client_process.os.environ["CLAUDE_CONFIG_DIR"] == str(live_config)
