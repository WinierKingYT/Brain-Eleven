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


def test_file_loaded_semantic_cli_uses_only_repository_root_bootstrap() -> None:
    """Its file-loaded dependency needs the package root, not scripts/ itself."""

    mutations = _sys_path_mutations("scripts/semantic-search.py")
    assert len(mutations) == 1
    assert ast.unparse(mutations[0].args[1]) == "str(_REPO_ROOT)"


def test_spawn_compatibility_adapters_retain_repository_bootstrap() -> None:
    """Bare legacy imports must remain discoverable in Windows spawn workers."""

    for relative_path in ("scripts/memory_store.py", "scripts/state_store.py"):
        mutations = _sys_path_mutations(relative_path)
        assert len(mutations) == 1
        assert ast.unparse(mutations[0].args[1]) == "str(_ROOT)"


def test_search_api_keeps_only_repository_root_bootstrap() -> None:
    mutations = _sys_path_mutations("scripts/search-api.py")

    assert len(mutations) == 1
    assert ast.unparse(mutations[0].args[1]) == "str(REPO_ROOT)"

    source = (ROOT / "scripts" / "search-api.py").read_text(encoding="utf-8")
    assert "from brain_eleven.runtime.chat_interface import ChatAgent" in source
    assert "from brain_eleven.runtime.capture_safety import" in source
    assert "from chat_interface import ChatAgent" not in source
    assert "from capture_safety import" not in source


def test_memory_validator_uses_the_runtime_safety_surface() -> None:
    source = (ROOT / "scripts" / "memory-validator.py").read_text(encoding="utf-8")

    assert "from brain_eleven.runtime.capture_safety import" in source
    assert "from capture_safety import" not in source
