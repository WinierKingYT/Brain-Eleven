#!/usr/bin/env python3
"""Compatibility adapter for the canonical support logging implementation."""

from __future__ import annotations

import sys
import importlib.util
from pathlib import Path
from types import ModuleType


_ROOT = Path(__file__).resolve().parents[1]
_CANONICAL_NAME = "brain_eleven.support.logging"


def _load_canonical() -> ModuleType:
    """Load the package module without re-entering support ``__init__``."""

    existing = sys.modules.get(_CANONICAL_NAME)
    if existing is not None:
        return existing

    module_path = _ROOT / "brain_eleven" / "support" / "logging.py"
    specification = importlib.util.spec_from_file_location(
        _CANONICAL_NAME,
        module_path,
    )
    if specification is None or specification.loader is None:
        raise ImportError(f"Cannot load canonical logging module: {module_path}")

    module = importlib.util.module_from_spec(specification)
    sys.modules[_CANONICAL_NAME] = module
    try:
        specification.loader.exec_module(module)
    except Exception:
        sys.modules.pop(_CANONICAL_NAME, None)
        raise
    return module


_logging = _load_canonical()
ColoredFormatter = _logging.ColoredFormatter
JSONFormatter = _logging.JSONFormatter
logger = _logging.logger
setup_logging = _logging.setup_logging


__all__ = ["ColoredFormatter", "JSONFormatter", "logger", "setup_logging"]

# Keep the historical bare import name available for callers that loaded the
# script directly before the package migration.
if __name__ == "scripts.logging_config":
    sys.modules.setdefault("logging_config", sys.modules[__name__])


if __name__ == "__main__":
    logger.debug("Debug message")
    logger.info("Info message")
    logger.warning("Warning message")
    logger.error("Error message")
    logger.critical("Critical message")

    print("\n✅ Logging configured")
    print("  Console: colorized output (INFO+)")
    print("  File logs/brain-eleven.log: all levels (JSON)")
    print("  File logs/brain-eleven.error.log: errors only (JSON)")
