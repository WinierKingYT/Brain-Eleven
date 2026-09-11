"""Canonical duplicate-memory planning and cleanup entrypoint.

The historical ``scripts/dedupe-validated-memory.py`` module remains a thin
compatibility/direct-execution adapter. Planning is read-only; ``main`` only
mutates canonical memory when ``--apply`` is explicitly supplied, and the
actual write continues through ``MemoryLifecycleManager``'s optimistic
``MemoryStore`` replacement path.
"""

from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path
from typing import Iterable, Sequence

from . import MemoryLifecycleManager


SUPERSESSION_NOTE = (
    "Auto-dedupe: exact dedup_fingerprint duplicate of canonical {canonical} "
    "(historical duplicate-ULID artifact)"
)


def plan_dedupe(memories: Iterable[dict]) -> list[tuple[str, str, str, str]]:
    """Return ``(loser, canonical, fingerprint, preview)`` actions.

    The earliest timestamp wins. ``memory_id`` is an explicit secondary key
    so equal-timestamp records have a stable winner independent of list order.
    """

    clusters: dict[str, list[dict]] = defaultdict(list)
    for memory in memories:
        fingerprint = memory.get("dedup_fingerprint")
        if fingerprint:
            clusters[fingerprint].append(memory)

    actions: list[tuple[str, str, str, str]] = []
    for fingerprint, group in clusters.items():
        active = [memory for memory in group if memory.get("status") != "superseded"]
        if len(active) < 2:
            continue

        # ISO-8601 timestamps sort lexically. memory_id makes ties explicit.
        active.sort(key=lambda memory: (
            memory.get("timestamp", ""),
            memory.get("memory_id", ""),
        ))
        canonical = active[0]
        for loser in active[1:]:
            actions.append((
                loser["memory_id"],
                canonical["memory_id"],
                fingerprint,
                " ".join(loser.get("content", "").split())[:70],
            ))
    return actions


def main(argv: Sequence[str] | None = None) -> int:
    """Run the historical dry-run/apply CLI."""

    arguments = list(sys.argv[1:] if argv is None else argv)
    apply = "--apply" in arguments
    positional = [argument for argument in arguments if not argument.startswith("--")]
    vault = Path(positional[0]) if positional else Path.home() / "Documents/Brain-Eleven"

    manager = MemoryLifecycleManager(str(vault))
    if not manager.memories:
        print(f"No validated memories found under {vault}")
        return 1

    actions = plan_dedupe(manager.memories)
    if not actions:
        print("✅ No duplicate fingerprint clusters to collapse.")
        return 0

    cluster_count = len({fingerprint for _, _, fingerprint, _ in actions})
    print(f"{len(actions)} duplicate record(s) across {cluster_count} "
          "fingerprint cluster(s):\n")
    for loser, canonical, fingerprint, preview in actions:
        print(f"  {loser}  ->  superseded_by {canonical}   [{fingerprint}]")
        print(f"      {preview}...")

    if not apply:
        print("\nDry run. Re-run with --apply to write these changes.")
        return 0

    for loser, canonical, _fingerprint, _preview in actions:
        manager.supersede_memory(
            loser,
            canonical,
            SUPERSESSION_NOTE.format(canonical=canonical),
        )
    manager.save()
    print(f"\n✅ Collapsed {len(actions)} duplicate(s); "
          f"{cluster_count} cluster(s) now have a single active memory_id.")
    return 0


__all__ = ["SUPERSESSION_NOTE", "MemoryLifecycleManager", "plan_dedupe", "main"]


if __name__ == "__main__":
    raise SystemExit(main())
