#!/usr/bin/env python3
"""
One-off cleanup: collapse pre-existing duplicate memories in
validated-memory.json that share a dedup_fingerprint but were minted with
separate memory_ids.

These are a historical artifact: early runs wrote records before
dedup_fingerprint was populated, so a later run's fingerprint match found
nothing, minted fresh ULIDs, and carried the fingerprint-less originals
forward untouched. A migration later back-filled dedup_fingerprint onto
both, leaving "same fingerprint, two memory_ids, both active" clusters that
anomaly_detector.py's detect_duplicate_content flags.

The forward fix lives in memory-validator.py (_canonical_by_fingerprint,
which now scans the whole persisted store and binds to the earliest record).
This script repairs the rows that predate that fix.

For each fingerprint cluster with >1 active record:
  - keep the EARLIEST memory_id (by timestamp) as canonical
  - mark every later record status="superseded", superseded_by=<canonical>,
    supersession_note=<why>, resolved_at=<now>

Records are preserved, not deleted, so lifecycle/provenance stays intact -
this reuses MemoryLifecycleManager.supersede_memory(), the same supersede
path memory-lifecycle.py exposes on the CLI.

Usage:
  python scripts/dedupe-validated-memory.py                 # dry run (default)
  python scripts/dedupe-validated-memory.py --apply         # write changes
  python scripts/dedupe-validated-memory.py --apply <vault> # non-default vault
"""

import sys
from collections import defaultdict
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from brain_eleven.lifecycle import MemoryLifecycleManager  # noqa: E402

SUPERSESSION_NOTE = (
    "Auto-dedupe: exact dedup_fingerprint duplicate of canonical {canonical} "
    "(historical duplicate-ULID artifact)"
)


def plan_dedupe(memories):
    """Return [(loser_id, canonical_id, fingerprint, content_preview), ...]."""
    clusters = defaultdict(list)
    for mem in memories:
        fp = mem.get("dedup_fingerprint")
        if fp:
            clusters[fp].append(mem)

    actions = []
    for fp, group in clusters.items():
        active = [m for m in group if m.get("status") != "superseded"]
        if len(active) < 2:
            continue
        # Earliest timestamp is canonical; ISO-8601 sorts lexically.
        active.sort(key=lambda m: m.get("timestamp", ""))
        canonical = active[0]
        for loser in active[1:]:
            actions.append((
                loser["memory_id"],
                canonical["memory_id"],
                fp,
                " ".join(loser.get("content", "").split())[:70],
            ))
    return actions


def main(argv):
    apply = "--apply" in argv
    positional = [a for a in argv if not a.startswith("--")]
    vault = Path(positional[0]) if positional else Path.home() / "Documents/Brain-Eleven"

    manager = MemoryLifecycleManager(str(vault))
    if not manager.memories:
        print(f"No validated memories found under {vault}")
        return 1

    actions = plan_dedupe(manager.memories)
    if not actions:
        print("✅ No duplicate fingerprint clusters to collapse.")
        return 0

    cluster_count = len({fp for _, _, fp, _ in actions})
    print(f"{len(actions)} duplicate record(s) across {cluster_count} "
          f"fingerprint cluster(s):\n")
    for loser, canonical, fp, preview in actions:
        print(f"  {loser}  ->  superseded_by {canonical}   [{fp}]")
        print(f"      {preview}...")

    if not apply:
        print("\nDry run. Re-run with --apply to write these changes.")
        return 0

    for loser, canonical, _fp, _preview in actions:
        manager.supersede_memory(
            loser, canonical, SUPERSESSION_NOTE.format(canonical=canonical)
        )
    manager.save()
    print(f"\n✅ Collapsed {len(actions)} duplicate(s); "
          f"{cluster_count} cluster(s) now have a single active memory_id.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
