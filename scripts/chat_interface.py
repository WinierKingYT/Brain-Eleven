#!/usr/bin/env python3
"""Compatibility adapter for the canonical runtime chat interface."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from contextlib import redirect_stdout
from pathlib import Path
from types import ModuleType


_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    # Historical direct execution starts with ``scripts/`` on sys.path.
    sys.path.insert(0, str(_ROOT))


def _configure_utf8_output() -> None:
    """Keep direct CLI diagnostics safe on Windows legacy code pages."""

    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")


_configure_utf8_output()

# Keep the migration contract explicit: callers depend on these packaged
# surfaces, never on the old implementation modules.
from brain_eleven.graph import KnowledgeGraph  # noqa: F401,E402
from brain_eleven.memory.scope import filter_memories  # noqa: F401,E402
from brain_eleven.search import HybridSearchEngine, MemoryRetriever  # noqa: F401,E402
from brain_eleven.support import (  # noqa: F401,E402
    AnomalyDetector,
    MemorySummarizer,
    setup_logging,
)


def _load_canonical(name: str, path: Path) -> ModuleType:
    """Load and cache the package implementation for legacy entrypoints."""

    existing = sys.modules.get(name)
    if existing is not None:
        return existing

    specification = importlib.util.spec_from_file_location(name, path)
    if specification is None or specification.loader is None:
        raise ImportError(f"Cannot load canonical module: {path}")

    module = importlib.util.module_from_spec(specification)
    sys.modules[name] = module
    try:
        specification.loader.exec_module(module)
    except Exception:
        sys.modules.pop(name, None)
        raise
    return module


_chat = _load_canonical(
    "brain_eleven.runtime.chat_interface",
    _ROOT / "brain_eleven" / "runtime" / "chat_interface.py",
)

ChatAgent = _chat.ChatAgent
ConversationContext = _chat.ConversationContext
Intent = _chat.Intent
IntentClassifier = _chat.IntentClassifier
logger = _chat.logger

__all__ = ["ChatAgent", "ConversationContext", "Intent", "IntentClassifier", "logger"]

# Preserve the historical bare module name used by direct imports and pytest.
if __name__ == "scripts.chat_interface":
    sys.modules.setdefault("chat_interface", sys.modules[__name__])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Chat with the Brain-Eleven memory system")
    parser.add_argument("--vault", default=".", help="Path to vault root")
    parser.add_argument("message", help="Message to send")
    args = parser.parse_args()

    with redirect_stdout(sys.stderr):
        agent = ChatAgent(vault_path=args.vault)
    result = agent.chat(args.message)
    print(json.dumps(result, indent=2, ensure_ascii=False))
