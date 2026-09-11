#!/usr/bin/env python3
"""Compatibility adapter for the canonical support anomaly detectors."""

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
    # sys.path; canonical anomaly imports the package memory scope surface.
    sys.path.insert(0, str(_ROOT))


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
_load_canonical(
    "brain_eleven.support.summarizer",
    _ROOT / "brain_eleven" / "support" / "summarizer.py",
)
_anomaly = _load_canonical(
    "brain_eleven.support.anomaly",
    _ROOT / "brain_eleven" / "support" / "anomaly.py",
)

AnomalyDetector = _anomaly.AnomalyDetector
jaccard_similarity = _anomaly.jaccard_similarity
logger = _anomaly.logger
tokenize = _anomaly.tokenize

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
