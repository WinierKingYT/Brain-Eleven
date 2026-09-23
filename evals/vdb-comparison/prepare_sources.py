"""Write IG01E-real's 48 fixture memories as individual files for vdb ingestion.

Usage:
    python prepare_sources.py <output_sources_dir>

The output directory must be ``<VDB_DATA_DIR>/sources`` (or a subdirectory of
it) -- the vdb project's ``ingest-dir`` command rejects a source directory
outside its configured ``VDB_DATA_DIR/sources`` root.

After this, ingest with (from the vdb project directory, with VDB_DATA_DIR,
VDB_QDRANT_URL and VDB_COLLECTION_NAME set to an isolated eval path/collection
-- never the vdb project's own production data):

    uv run vdb ingest-dir <output_sources_dir>
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "evals" / "ig01e_real" / "fixtures" / "real-content-v1.json"


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    out_dir = Path(sys.argv[1])
    out_dir.mkdir(parents=True, exist_ok=True)
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    for memory in fixture["memories"]:
        (out_dir / f"{memory['memory_id']}.md").write_text(memory["content"], encoding="utf-8")
    print(f"wrote {len(fixture['memories'])} files to {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
