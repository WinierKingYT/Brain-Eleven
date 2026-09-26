#!/usr/bin/env python3
"""Read-only: compare SessionStart's old top-5 with the step-9 distinct selection.

For each registered project, reports how many of the old five bootstrap
slots went to near-duplicates of an earlier slot or to stale_candidate
memories, and which memory ids the new selection adds or drops. Prints ids
and counts only, never memory text.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from brain_eleven._legacy import load_legacy_module  # noqa: E402
from brain_eleven.projects.registry import ProjectRegistry  # noqa: E402
from brain_eleven.runtime.context import BOOTSTRAP_POOL, NEAR_DUPLICATE, _stale_memory_ids, select_distinct  # noqa: E402
from brain_eleven.runtime.review import _words  # noqa: E402


def _redundant(chosen):
    seen, count = [], 0
    for memory in chosen:
        words = _words(memory.get("content", ""))
        if any(words and w and len(words & w) / len(words | w) >= NEAR_DUPLICATE for w in seen):
            count += 1
        seen.append(words)
    return count


def compare(vault) -> dict:
    """Old vs step-9 bootstrap slots for every registered project."""
    compiler_type = load_legacy_module("brain_eleven_legacy_context_compiler", "context-compiler.py").ContextCompiler
    stale = _stale_memory_ids(vault)
    report = {}
    for project in ProjectRegistry(vault).list_projects():
        compiler = compiler_type(str(vault), project_id=project["project_id"])
        compiler.memories = compiler.memory_store.load()["validated_memory"]
        compiler._resolve_current_state()
        pool = compiler._rank_memories(limit=BOOTSTRAP_POOL)
        old, new = pool[:5], select_distinct(pool, stale_ids=stale, limit=5)
        old_ids, new_ids = [m["memory_id"] for m in old], [m["memory_id"] for m in new]
        report[Path(str(project.get("root", ""))).name or project["project_id"]] = {
            "pool": len(pool),
            "old_near_duplicate_slots": _redundant(old), "old_stale_slots": sum(i in stale for i in old_ids),
            "new_near_duplicate_slots": _redundant(new), "new_stale_slots": sum(i in stale for i in new_ids),
            "added": [i for i in new_ids if i not in old_ids], "dropped": [i for i in old_ids if i not in new_ids]}
    return report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--vault", default=".")
    print(json.dumps(compare(parser.parse_args(argv).vault), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
