"""Repository-wide pytest aliases for the remaining ``scripts`` modules.

Tests import these by their bare names; aliasing them here avoids changing
``sys.path``.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path


_ROOT = Path(__file__).parent


def _alias_package_module(name: str) -> None:
    if not (_ROOT / "scripts" / f"{name}.py").exists():
        return
    module = importlib.import_module(f"scripts.{name}")
    sys.modules.setdefault(name, module)


for _module_name in (
    "memory_backup",
    "remember",
    "remember_opt_in",
):
    _alias_package_module(_module_name)
