#!/usr/bin/env python3
"""Compatibility adapter for the canonical support anomaly detectors."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    # The historical direct-execution entrypoint starts with ``scripts/`` on
    # sys.path; canonical anomaly imports the package memory scope surface.
    sys.path.insert(0, str(_ROOT))


from brain_eleven.support.anomaly import (  # noqa: E402
    AnomalyDetector,
    jaccard_similarity,
    logger,
    tokenize,
)

__all__ = ["AnomalyDetector", "jaccard_similarity", "logger", "tokenize"]

# Keep the historical bare import name available for callers that imported
# the script before the package migration.
if __name__ == "scripts.anomaly_detector":
    sys.modules.setdefault("anomaly_detector", sys.modules[__name__])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Scan Brain-Eleven memory store for anomalies")
    parser.add_argument("--vault", default=".", help="Path to vault root")
    parser.add_argument("--json", action="store_true", help="Output raw JSON instead of Markdown")
    args = parser.parse_args()

    detector = AnomalyDetector(vault_path=args.vault)
    report = detector.detect_all()

    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print(detector.to_markdown(report))
