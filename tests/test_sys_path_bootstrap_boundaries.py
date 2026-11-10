"""Guard the bounded reduction of legacy script import bootstraps."""

from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _sys_path_mutations(relative_path: str) -> list[ast.Call]:
    source = (ROOT / relative_path).read_text(encoding="utf-8")
    tree = ast.parse(source, filename=relative_path)
    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in {"append", "insert"}
        and isinstance(node.func.value, ast.Attribute)
        and isinstance(node.func.value.value, ast.Name)
        and node.func.value.value.id == "sys"
        and node.func.value.attr == "path"
    ]


def test_memory_validator_uses_the_runtime_safety_surface() -> None:
    source = (ROOT / "brain_eleven" / "memory" / "validator.py").read_text(encoding="utf-8")

    assert "from brain_eleven.runtime.capture_safety import" in source
    assert "from capture_safety import" not in source
