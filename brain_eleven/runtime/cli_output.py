"""Command-line output helpers shared by the machine-readable runtime contracts."""

from __future__ import annotations

import sys


def use_utf8_stdout() -> None:
    """Emit UTF-8 on stdout regardless of the platform's legacy code page.

    The JSON contracts are rendered with ``ensure_ascii=False``. A Windows pipe
    otherwise inherits the ANSI code page (cp1252 on en-US), which cannot encode
    characters such as U+0131 and aborts the command before any output. Only
    CLI entrypoints call this; library functions never change a global stream.
    """
    reconfigure = getattr(sys.stdout, "reconfigure", None)
    if reconfigure is not None:
        reconfigure(encoding="utf-8", errors="strict")
