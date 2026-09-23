"""Score run_search.py's raw vdb results with Brain-Eleven's own, unmodified
precision@min(5,|relevant|) metric (evals.ig01d.d0_recheck._metric_row_recheck),
so the number is directly comparable to IG01E's real-content precision_at_min5_relevant.

Usage: python score_results.py <results.json>
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from evals.ig01d.d0_recheck import _aggregate_recheck, _metric_row_recheck  # noqa: E402


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    results = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))

    rows = []
    leakage_events = []
    for r in results:
        metrics = _metric_row_recheck(r["retrieved"], r["required"], r["useful"])
        rows.append({"task_id": r["task_id"], **metrics})
        forbidden_hit = [mid for mid in r["retrieved"][:5] if mid in r["forbidden"]]
        if forbidden_hit:
            leakage_events.append((r["task_id"], forbidden_hit))

    agg = _aggregate_recheck(rows)
    print(f"=== {sys.argv[1]} ({len(results)} cases) ===")
    for key, value in agg.items():
        print(f"{key}: {value}")
    print(f"forbidden leakage in top-5: {len(leakage_events)} of {len(results)} cases")
    for task_id, items in leakage_events:
        print(f"  - {task_id}: {items}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
