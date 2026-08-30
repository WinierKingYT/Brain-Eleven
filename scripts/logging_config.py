#!/usr/bin/env python3
"""
Logging Configuration for Brain-Eleven v3
Structured JSON logging with console and file output
"""

import logging
import json
from datetime import datetime, timezone
from pathlib import Path

class JSONFormatter(logging.Formatter):
    """Custom JSON formatter for structured logging"""

    def format(self, record):
        log_obj = {
            # datetime.utcnow() is deprecated (returns a naive datetime that's
            # easy to mistake for local time) - timezone.utc makes the UTC-ness
            # explicit in the ISO string itself (trailing +00:00).
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
    """Colored formatter for console output"""

    COLORS = {
        'DEBUG': '\033[36m',      # Cyan
        'INFO': '\033[32m',       # Green
        'WARNING': '\033[33m',    # Yellow
        'ERROR': '\033[31m',      # Red
        'CRITICAL': '\033[35m',   # Magenta
    }
    RESET = '\033[0m'

    def format(self, record):
        levelname = record.levelname
        color = self.COLORS.get(levelname, self.RESET)

        # Format: [HH:MM:SS] LEVEL logger message
        timestamp = datetime.fromtimestamp(record.created).strftime('%H:%M:%S')
        formatted = f"{color}[{timestamp}] {levelname:<8}{self.RESET} {record.name}: {record.getMessage()}"

        if record.exc_info:
            formatted += "\n" + self.formatException(record.exc_info)

        return formatted

def setup_logging(name: str, log_dir: str = "logs") -> logging.Logger:
    """
    Setup logging for a module

    Args:
        name: Logger name (usually __name__)
        log_dir: Directory for log files

    Returns:
        Configured logger instance
    """

    logger = logging.getLogger(name)

    # Avoid duplicate handlers
    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG)

    # Create logs directory
    log_path = Path(log_dir)
    log_path.mkdir(exist_ok=True)

    # Console handler (INFO level)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(ColoredFormatter())
    logger.addHandler(console_handler)

    # File handler (DEBUG level)
    file_handler = logging.FileHandler(log_path / "brain-eleven.log")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(JSONFormatter())
    logger.addHandler(file_handler)

    # Error file handler (ERROR level)
    error_handler = logging.FileHandler(log_path / "brain-eleven.error.log")
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(JSONFormatter())
    logger.addHandler(error_handler)

    return logger

# Module-level logger
logger = setup_logging(__name__)

if __name__ == "__main__":
    # Test logging
    logger.debug("Debug message")
    logger.info("Info message")
    logger.warning("Warning message")
    logger.error("Error message")
    logger.critical("Critical message")

    print("\n✅ Logging configured")
    print("  Console: colorized output (INFO+)")
    print("  File logs/brain-eleven.log: all levels (JSON)")
    print("  File logs/brain-eleven.error.log: errors only (JSON)")
