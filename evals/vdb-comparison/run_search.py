"""Run IG01E-real's 21 real task prompts through an external vdb (personal
vector database, https://github.com -- Ahmet's own separate project, not
part of this repo) instance and save the raw ranked results.

This is a read-only, external-tool comparison probe: it never modifies vdb's
production data (an isolated VDB_DATA_DIR/VDB_QDRANT_URL/VDB_COLLECTION_NAME
must be set -- see prepare_sources.py) and never modifies Brain-Eleven's own
retrieval code. Score the output with score_results.py, which reuses Brain-
Eleven's own evals.ig01d.d0_recheck._metric_row_recheck unmodified, so the
number is directly comparable to IG01E's own precision_at_min5_relevant.

Usage (from this repo's root, after prepare_sources.py + `vdb ingest-dir`):
    python run_search.py <vdb_project_dir> <vdb_data_dir> <output.json> [--rerank]

Requires VDB_RERANKER_MODE=lexical in the environment (or a project .env) for
--rerank to work; vdb's own reranker is a lexical/term-overlap reranker, not
a neural cross-encoder -- see the evidence report for why that distinction
matters here.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def load_tasks() -> list[dict]:
    tasks = []
    for path in sorted((ROOT / "evals" / "ig01e_real" / "tasks").glob("real_*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        tasks.append({
            "task_id": data["task_id"],
            "prompt": data["task"]["prompt"],
            "required": data["expected_context"]["required"],
            "useful": data["expected_context"]["useful"],
            "forbidden": data["expected_context"]["forbidden"],
        })
    return tasks


def main() -> int:
    if len(sys.argv) < 4:
        print(__doc__)
        return 2
    vdb_dir, vdb_data_dir, output_path = sys.argv[1:4]
    rerank = "--rerank" in sys.argv[4:]

    tasks = load_tasks()
    env = dict(os.environ)
    env.update({
        "VDB_DATA_DIR": vdb_data_dir,
        "VDB_QDRANT_URL": f"path:{Path(vdb_data_dir) / 'qdrant_storage'}",
        "VDB_COLLECTION_NAME": "brain_eleven_ig01e_eval_v1",
    })

    results = []
    for i, task in enumerate(tasks):
        command = ["uv", "run", "vdb", "search", task["prompt"], "--limit", "5"]
        if rerank:
            command.append("--rerank")
        completed = subprocess.run(
            command, cwd=vdb_dir, env=env, capture_output=True, text=True, timeout=60,
        )
        retrieved = []
        for line in completed.stdout.splitlines():
            if not line.strip() or "\t" not in line:
                continue
            parts = line.split("\t")
            if len(parts) < 3:
                continue
            fname = parts[2].rsplit("/", 1)[-1]
            retrieved.append(fname[:-3] if fname.endswith(".md") else fname)
        results.append({**task, "retrieved": retrieved})
        print(f"[{i + 1}/{len(tasks)}] {task['task_id']}: retrieved={retrieved}", file=sys.stderr)
        if completed.returncode != 0:
            print(f"  STDERR: {completed.stderr[-500:]}", file=sys.stderr)

    Path(output_path).write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"done, wrote {len(results)} results to {output_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
