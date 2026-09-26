#!/usr/bin/env python3
"""Read-only review-queue noise report (roadmap step 4: measure before filtering).

Groups every review candidate under ``.brain-eleven/runtime/review`` by why
it was queued (reason), what it is (candidate_type / memory_type), where it
came from (source client / role) and how it ended (PENDING / ACCEPTED /
REJECTED / EXPIRED, duplicate or not). For each group it reports the human
acceptance rate among decided items, so the noisiest categories are visible
before any filter is written. Prints counts and content-length buckets only;
never candidate text.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable


def _length_bucket(n: int) -> str:
    for limit in (40, 120, 400, 1500):
        if n <= limit:
            return f"<={limit}"
    return ">1500"


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from brain_eleven.runtime.review import content_shape as _shape  # noqa: E402


def load_items(vault: Path) -> Iterable[dict[str, Any]]:
    for path in sorted((vault / ".brain-eleven" / "runtime" / "review").glob("rev_*.json")):
        try:
            item = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(item, dict):
            yield item


def report(items: Iterable[dict[str, Any]]) -> dict[str, Any]:
    dimensions = ("reason", "candidate_type", "memory_type", "commitment", "shape", "reason_x_shape",
                  "source_role", "source_client", "project_id", "content_length")
    groups: dict[str, dict[str, Counter]] = {d: defaultdict(Counter) for d in dimensions}
    totals: Counter = Counter()
    for item in items:
        candidate = item.get("candidate") if isinstance(item.get("candidate"), dict) else {}
        source = item.get("source") if isinstance(item.get("source"), dict) else {}
        text = candidate.get("text") if candidate.get("candidate_type") == "STATE_MUTATION" else candidate.get("content")
        status = str(item.get("status"))
        if item.get("duplicate_of"):
            status = "DUPLICATE_" + status
        values = {
            "reason": item.get("reason"), "candidate_type": candidate.get("candidate_type"),
            "memory_type": candidate.get("memory_type"), "source_role": source.get("role"),
            "source_client": source.get("client"), "project_id": item.get("project_id"),
            "content_length": _length_bucket(len(text)) if isinstance(text, str) else None,
            "commitment": candidate.get("commitment"),
            "shape": _shape(text) if isinstance(text, str) else None,
        }
        values["reason_x_shape"] = f"{values['reason']}|{values['shape']}"
        totals[status] += 1
        for dimension, value in values.items():
            groups[dimension][str(value)][status] += 1

    def summarize(counter: Counter) -> dict[str, Any]:
        accepted, rejected = counter.get("ACCEPTED", 0), counter.get("REJECTED", 0)
        decided = accepted + rejected
        return {**dict(counter), "total": sum(counter.values()),
                "acceptance_rate": round(accepted / decided, 3) if decided else None}

    return {"totals": summarize(totals),
            "by": {d: {k: summarize(v) for k, v in sorted(g.items(), key=lambda kv: -sum(kv[1].values()))}
                   for d, g in groups.items()}}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--vault", default=".")
    args = parser.parse_args(argv)
    print(json.dumps(report(load_items(Path(args.vault))), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
