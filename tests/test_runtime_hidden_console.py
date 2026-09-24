"""The runtime service must own a hidden console on Windows.

2026-09-24: hooks run pythonw.exe, the service inherited it, and a console-less
service made every provider CLI it started (hermes.EXE) open a visible window.
"""

import os

import pytest

from brain_eleven.runtime import launcher

pytestmark = pytest.mark.skipif(os.name != "nt", reason="console subsystems are Windows-only")


def test_service_uses_console_python_when_hooks_run_pythonw(tmp_path, monkeypatch):
    (tmp_path / "pythonw.exe").write_text("", encoding="utf-8")
    (tmp_path / "python.exe").write_text("", encoding="utf-8")
    monkeypatch.setattr(launcher.sys, "executable", str(tmp_path / "pythonw.exe"))
    assert launcher._service_interpreter() == str(tmp_path / "python.exe")


def test_service_keeps_pythonw_when_no_console_sibling_exists(tmp_path, monkeypatch):
    (tmp_path / "pythonw.exe").write_text("", encoding="utf-8")
    monkeypatch.setattr(launcher.sys, "executable", str(tmp_path / "pythonw.exe"))
    assert launcher._service_interpreter() == str(tmp_path / "pythonw.exe")


def test_service_keeps_console_python_unchanged(tmp_path, monkeypatch):
    (tmp_path / "python.exe").write_text("", encoding="utf-8")
    monkeypatch.setattr(launcher.sys, "executable", str(tmp_path / "python.exe"))
    assert launcher._service_interpreter() == str(tmp_path / "python.exe")
