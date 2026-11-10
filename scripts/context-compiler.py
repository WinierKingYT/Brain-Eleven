#!/usr/bin/env python3
"""Installed-hook entry point for the context compiler.

The SessionStart hook template (and hooks already installed from it) run this
file path. The implementation lives in ``brain_eleven.runtime.context_compiler``.
"""

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from brain_eleven.runtime.context_compiler import main  # noqa: E402

if __name__ == "__main__":
    main()
