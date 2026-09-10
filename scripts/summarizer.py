#!/usr/bin/env python3
"""Compatibility adapter for the canonical support summarizer."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType


_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    # The historical direct-execution entrypoint starts with ``scripts/`` on
    # sys.path; the canonical module also imports ``brain_eleven.memory``.
    sys.path.insert(0, str(_ROOT))

from brain_eleven.memory import filter_memories, infer_memory_scope


def _load_canonical(name: str, path: Path) -> ModuleType:
    """Load a canonical support module once for old script entrypoints."""

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


_load_canonical(
    "brain_eleven.support.logging",
    _ROOT / "brain_eleven" / "support" / "logging.py",
)
_summarizer = _load_canonical(
    "brain_eleven.support.summarizer",
    _ROOT / "brain_eleven" / "support" / "summarizer.py",
)

MemorySummarizer = _summarizer.MemorySummarizer
STOPWORDS = _summarizer.STOPWORDS
jaccard_similarity = _summarizer.jaccard_similarity
logger = _summarizer.logger
tokenize = _summarizer.tokenize

__all__ = [
    "MemorySummarizer",
    "STOPWORDS",
    "filter_memories",
    "infer_memory_scope",
    "jaccard_similarity",
    "logger",
    "tokenize",
]

# Keep the historical bare import name available for callers that imported
# the script before the package migration.
if __name__ == "scripts.summarizer":
    sys.modules.setdefault("summarizer", sys.modules[__name__])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate a Brain-Eleven memory digest")
    parser.add_argument("--vault", default=".", help="Path to vault root")
    parser.add_argument("--days", type=int, default=None, help="Only include last N days")
    parser.add_argument("--top-n", type=int, default=5, help="Max entries per type")
    parser.add_argument("--json", action="store_true", help="Output raw JSON instead of Markdown")
    args = parser.parse_args()

    summarizer = MemorySummarizer(vault_path=args.vault)
    digest = summarizer.generate_digest(days=args.days, top_n_per_type=args.top_n)

    if args.json:
        print(json.dumps(digest, indent=2, ensure_ascii=False))
    else:
        print(summarizer.to_markdown(digest))
