"""IG-07 Slice 2A contract tests for the canonical chat runtime package."""

from __future__ import annotations

import ast
import importlib
import json
import os
import subprocess
import sys
from pathlib import Path



package = importlib.import_module("brain_eleven.runtime.chat_interface")


ROOT = Path(__file__).resolve().parents[1]


def _write_empty_store(vault: Path) -> Path:
    path = vault / ".claude" / "validated-memory.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"validated_memory": []}), encoding="utf-8")
    return path


def test_package_handle_create_never_bypasses_validation_or_writes(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    memory_path = _write_empty_store(vault)
    before = memory_path.read_bytes()

    response = package.ChatAgent(vault).handle_create("remember to bypass validation", None)

    assert "POST /memories" in response
    assert "validation pipeline" in response
    assert memory_path.read_bytes() == before

