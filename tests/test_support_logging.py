"""Contract tests for the IG-07 support logging migration."""

from __future__ import annotations

import ast
import importlib
import json
import logging
import os
import subprocess
import sys
from pathlib import Path

from brain_eleven.support.logging import (
    ColoredFormatter,
    JSONFormatter,
    setup_logging,
)


ROOT = Path(__file__).resolve().parents[1]


def _clean_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()
    logger.setLevel(logging.NOTSET)
    return logger


def _record(*, level: int = logging.INFO, **kwargs: object) -> logging.LogRecord:
    defaults = {
        "name": "ig07.logging",
        "level": level,
        "pathname": str(ROOT / "sample.py"),
        "lineno": 42,
        "msg": "hello %s",
        "args": ("world",),
        "exc_info": None,
        "func": "<module>",
    }
    defaults.update(kwargs)
    return logging.LogRecord(**defaults)


def test_json_formatter_serializes_contract_fields() -> None:
    payload = json.loads(JSONFormatter().format(_record()))

    assert payload["level"] == "INFO"
    assert payload["logger"] == "ig07.logging"
    assert payload["message"] == "hello world"
    assert payload["module"] == "sample"
    assert payload["function"] == "<module>"
    assert payload["line"] == 42
    assert payload["timestamp"].endswith("+00:00")


def test_json_formatter_serializes_exception_as_valid_json_string() -> None:
    try:
        raise ValueError("boom")
    except ValueError:
        record = _record(level=logging.ERROR, exc_info=sys.exc_info())

    payload = json.loads(JSONFormatter().format(record))

    assert "ValueError: boom" in payload["exception"]
    assert isinstance(payload["exception"], str)


def test_colored_formatter_includes_level_and_exception() -> None:
    formatter = ColoredFormatter()
    rendered = formatter.format(_record(level=logging.WARNING))
    assert "WARNING" in rendered
    assert "ig07.logging" in rendered
    assert "\033[33m" in rendered


def test_setup_logging_is_idempotent_for_one_logger(tmp_path: Path) -> None:
    name = "ig07.tests.idempotent"
    logger = _clean_logger(name)
    try:
        first = setup_logging(name, str(tmp_path))
        second = setup_logging(name, str(tmp_path / "ignored"))

        assert first is logger
        assert second is first
        assert len(first.handlers) == 3
        assert not (tmp_path / "ignored").exists()
    finally:
        _clean_logger(name)


def test_setup_logging_uses_isolated_log_dir_and_serializes_levels(
    tmp_path: Path,
) -> None:
    name = "ig07.tests.isolated"
    log_dir = tmp_path / "isolated-logs"
    logger = _clean_logger(name)
    try:
        configured = setup_logging(name, str(log_dir))
        configured.debug("debug message")
        configured.error("error message")
        for handler in configured.handlers:
            handler.flush()

        debug_lines = (log_dir / "brain-eleven.log").read_text().splitlines()
        error_lines = (log_dir / "brain-eleven.error.log").read_text().splitlines()
        assert any(json.loads(line)["message"] == "debug message" for line in debug_lines)
        assert any(json.loads(line)["message"] == "error message" for line in debug_lines)
        assert all(json.loads(line)["level"] == "ERROR" for line in error_lines)
        assert all(json.loads(line)["message"] == "error message" for line in error_lines)
        assert sorted(path.name for path in log_dir.iterdir()) == [
            "brain-eleven.error.log",
            "brain-eleven.log",
        ]
    finally:
        _clean_logger(name)


def test_package_and_legacy_logging_objects_share_identity() -> None:
    legacy = importlib.import_module("scripts.logging_config")
    bare_legacy = importlib.import_module("logging_config")

    assert legacy.JSONFormatter is JSONFormatter
    assert legacy.ColoredFormatter is ColoredFormatter
    assert legacy.setup_logging is setup_logging
    assert bare_legacy.JSONFormatter is JSONFormatter
    assert bare_legacy.ColoredFormatter is ColoredFormatter
    assert bare_legacy.setup_logging is setup_logging


def test_legacy_file_is_only_an_adapter() -> None:
    source_path = ROOT / "scripts" / "logging_config.py"
    source = source_path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    assert "brain_eleven.support.logging" in source
    assert not {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ClassDef)
    } & {"JSONFormatter", "ColoredFormatter"}
    assert "def setup_logging" not in source


def test_direct_execution_uses_the_same_legacy_contract(tmp_path: Path) -> None:
    script = ROOT / "scripts" / "logging_config.py"
    environment = os.environ.copy()
    environment["PYTHONIOENCODING"] = "utf-8"
    result = subprocess.run(
        [sys.executable, str(script)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        env=environment,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "Logging configured" in result.stdout
    assert (tmp_path / "logs" / "brain-eleven.log").is_file()
    assert (tmp_path / "logs" / "brain-eleven.error.log").is_file()
