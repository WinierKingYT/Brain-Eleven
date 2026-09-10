"""Canonical logging implementation for the support package.

The historical :mod:`scripts.logging_config` module remains available as a
compatibility adapter, but all formatter and logger setup behavior lives here.
Keeping the implementation in the installable package gives legacy imports
and package imports one shared object identity during the migration.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path


class JSONFormatter(logging.Formatter):
    """Format records as structured JSON objects."""

    def format(self, record: logging.LogRecord) -> str:
        log_obj = {
            # ``datetime.utcnow()`` returns a naive datetime.  An explicit UTC
            # timezone keeps the serialized timestamp unambiguous.
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        if record.exc_info:
            log_obj["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_obj)


class ColoredFormatter(logging.Formatter):
    """Format console records with a timestamp and level color."""

    COLORS = {
        "DEBUG": "\033[36m",      # Cyan
        "INFO": "\033[32m",       # Green
        "WARNING": "\033[33m",   # Yellow
        "ERROR": "\033[31m",     # Red
        "CRITICAL": "\033[35m",  # Magenta
    }
    RESET = "\033[0m"

    def format(self, record: logging.LogRecord) -> str:
        levelname = record.levelname
        color = self.COLORS.get(levelname, self.RESET)

        timestamp = datetime.fromtimestamp(record.created).strftime("%H:%M:%S")
        formatted = (
            f"{color}[{timestamp}] {levelname:<8}{self.RESET} "
            f"{record.name}: {record.getMessage()}"
        )

        if record.exc_info:
            formatted += "\n" + self.formatException(record.exc_info)

        return formatted


def setup_logging(name: str, log_dir: str = "logs") -> logging.Logger:
    """Create the standard console, debug-file, and error-file handlers.

    Existing handlers are preserved so repeated setup calls for the same
    logger cannot duplicate output.  The directory and file names retain the
    legacy contract for callers that still import ``scripts.logging_config``.
    """

    logger = logging.getLogger(name)

    # Avoid duplicate handlers when a module is imported more than once.
    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG)

    log_path = Path(log_dir)
    log_path.mkdir(exist_ok=True)

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(ColoredFormatter())
    logger.addHandler(console_handler)

    file_handler = logging.FileHandler(log_path / "brain-eleven.log")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(JSONFormatter())
    logger.addHandler(file_handler)

    error_handler = logging.FileHandler(log_path / "brain-eleven.error.log")
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(JSONFormatter())
    logger.addHandler(error_handler)

    return logger


logger = setup_logging(__name__)


__all__ = ["ColoredFormatter", "JSONFormatter", "logger", "setup_logging"]
