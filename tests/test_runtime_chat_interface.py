"""IG-07 Slice 2A contract tests for the canonical chat runtime package."""

from __future__ import annotations

import ast
import importlib
import json
import os
import subprocess
import sys
from pathlib import Path

import chat_interface as legacy


package = importlib.import_module("brain_eleven.runtime.chat_interface")


ROOT = Path(__file__).resolve().parents[1]


def _write_empty_store(vault: Path) -> Path:
    path = vault / ".claude" / "validated-memory.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"validated_memory": []}), encoding="utf-8")
    return path


def test_package_and_legacy_surfaces_preserve_object_identity() -> None:
    assert package.ChatAgent is legacy.ChatAgent
    assert package.ConversationContext is legacy.ConversationContext
    assert package.Intent is legacy.Intent
    assert package.IntentClassifier is legacy.IntentClassifier


def test_legacy_script_is_an_adapter_without_chat_implementation() -> None:
    source = (ROOT / "scripts" / "chat_interface.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    defined_classes = {node.name for node in ast.walk(tree) if isinstance(node, ast.ClassDef)}
    defined_functions = {node.name for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}

    assert defined_classes == set()
    assert defined_functions == {"_configure_utf8_output", "_load_canonical"}
    assert "brain_eleven.runtime.chat_interface" in source
    assert "class ChatAgent" not in source
    assert "def handle_create" not in source


def test_intent_classification_parity_is_preserved() -> None:
    samples = [
        "what did we decide about SQLite?",
        "summarize this week",
        "show duplicate anomalies",
        "remember to update the docs",
        "analyze the Redis relationship",
        "what is connected to PostgreSQL?",
        "reflect on our lessons",
    ]
    package_classifier = package.IntentClassifier()
    legacy_classifier = legacy.IntentClassifier()

    assert [package_classifier.classify(sample) for sample in samples] == [
        legacy_classifier.classify(sample) for sample in samples
    ]


def test_package_handle_create_never_bypasses_validation_or_writes(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    memory_path = _write_empty_store(vault)
    before = memory_path.read_bytes()

    response = package.ChatAgent(vault).handle_create("remember to bypass validation", None)

    assert "POST /memories" in response
    assert "validation pipeline" in response
    assert memory_path.read_bytes() == before


def test_direct_legacy_cli_keeps_json_contract(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    _write_empty_store(vault)
    command = [sys.executable, str(ROOT / "scripts" / "chat_interface.py"), "--vault", str(vault), "hello"]
    kwargs = {"capture_output": True, "text": True, "encoding": "utf-8", "check": False}
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    result = subprocess.run(command, **kwargs)

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["intent"] == "QUERY"
    assert "response" in payload
    assert "conversation_id" in payload
