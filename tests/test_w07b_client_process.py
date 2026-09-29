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


def test_claude_subprocess_can_use_reusable_temp_profile(tmp_path: Path, monkeypatch):
    settings_dir = tmp_path / "run-settings"
    settings_dir.mkdir()
    profile = tmp_path / "authenticated-profile"
    monkeypatch.setenv("W07B_CLAUDE_CONFIG_DIR", str(profile))
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "host-profile"))

    env = client_process.claude_environment(settings_dir)

    assert env["CLAUDE_CONFIG_DIR"] == str(profile.resolve())
    assert "W07B_CLAUDE_CONFIG_DIR" not in env
    assert profile.is_dir()
    assert client_process.os.environ["CLAUDE_CONFIG_DIR"] == str(tmp_path / "host-profile")


def test_claude_subprocess_rejects_non_temp_profile_override(monkeypatch):
    monkeypatch.setenv("W07B_CLAUDE_CONFIG_DIR", str(Path.home() / ".claude"))

    try:
        client_process.claude_environment(Path.home() / ".claude")
    except RuntimeError as exc:
        assert str(exc) == "CLAUDE_CONFIG_NOT_ISOLATED"
    else:
        raise AssertionError("a host Claude profile must be rejected")
