#!/usr/bin/env python3
"""
Brain-Eleven v3 - Anomaly Detector (Phase 10B)

Rule-based detectors over the validated memory store. Deliberately
independent of embeddings/LLM (same reasoning as summarizer.py): these are
structural/statistical checks on metadata and content that already exist,
not semantic judgments.

Detectors:
- duplicate_content:      near-duplicate memories not marked superseded
- stale_open_loop:        open_loop still "active" past an age threshold
- low_confidence_outlier: approved memory with suspiciously low confidence
- quality_confidence_gap: quality_score and confidence disagree sharply
- burst_ingestion:        many memories created in the same instant (loop bug)
- broken_supersession:    superseded_by points at a memory_id that doesn't exist
- trivial_content:        content too short/empty to be a useful memory
"""

import json
import re
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional
from collections import defaultdict

from logging_config import setup_logging
from summarizer import tokenize, jaccard_similarity  # reuse Phase 10A helpers

logger = setup_logging(__name__)


class AnomalyDetector:
    """Runs structural/statistical checks over the memory store."""

    DUPLICATE_THRESHOLD = 0.6
    STALE_OPEN_LOOP_DAYS = 3
    LOW_CONFIDENCE_THRESHOLD = 0.3
    QUALITY_CONFIDENCE_GAP_THRESHOLD = 0.5
    BURST_INGESTION_MIN_COUNT = 15  # same-timestamp memories flagged as a burst
    TRIVIAL_CONTENT_MIN_LENGTH = 10

    SEVERITY_ORDER = {"critical": 0, "warning": 1, "info": 2}

    def __init__(self, vault_path: str = "."):
        self.vault_path = Path(vault_path)
        self.memory_file = self.vault_path / ".claude" / "validated-memory.json"

    def load_memories(self) -> List[Dict]:
        if not self.memory_file.exists():
            logger.warning(f"No memory file at {self.memory_file}")
            return []
        with open(self.memory_file, encoding="utf-8") as f:
            data = json.load(f)
        return data.get("validated_memory", [])

    @staticmethod
    def _short(content: str, limit: int = 80) -> str:
        content = content.replace("\n", " ").strip()
        return content if len(content) <= limit else content[:limit] + "..."

    # -- individual detectors ------------------------------------------------

    def detect_duplicate_content(self, memories: List[Dict]) -> List[Dict]:
        """Near-duplicate active memories that were never consolidated."""
        anomalies = []
        active = [m for m in memories if m.get("status") == "active"]

        for i, a in enumerate(active):
            for b in active[i + 1:]:
                if a.get("type") != b.get("type"):
                    continue
                similarity = jaccard_similarity(a.get("content", ""), b.get("content", ""))
                if similarity >= self.DUPLICATE_THRESHOLD:
                    anomalies.append({
                        "type": "duplicate_content",
                        "severity": "warning",
                        "memory_ids": [a.get("memory_id"), b.get("memory_id")],
                        "description": (
                            f"Near-duplicate {a.get('type')} memories "
                            f"(similarity {similarity:.2f}) never consolidated"
                        ),
                        "details": {
                            "a": self._short(a.get("content", "")),
                            "b": self._short(b.get("content", "")),
                        },
                    })
        return anomalies

    def detect_stale_open_loops(self, memories: List[Dict]) -> List[Dict]:
        """Open loops still active well past a reasonable staleness window."""
        anomalies = []
        now = datetime.now()

        for m in memories:
            if m.get("type") != "open_loop" or m.get("status") != "active":
                continue

            timestamp = m.get("timestamp", "")
            try:
                created = datetime.fromisoformat(timestamp)
            except (ValueError, TypeError):
                continue

            age_days = (now - created).total_seconds() / 86400
            if age_days >= self.STALE_OPEN_LOOP_DAYS:
                anomalies.append({
                    "type": "stale_open_loop",
                    "severity": "warning",
                    "memory_ids": [m.get("memory_id")],
                    "description": f"Open loop active for {age_days:.1f} days without resolution",
                    "details": {"content": self._short(m.get("content", ""))},
                })
        return anomalies

    def detect_low_confidence_outliers(self, memories: List[Dict]) -> List[Dict]:
        """Approved memories carrying suspiciously low confidence."""
        anomalies = []
        for m in memories:
            if not m.get("is_approved"):
                continue
            confidence = m.get("confidence", 1.0)
            if confidence < self.LOW_CONFIDENCE_THRESHOLD:
                anomalies.append({
                    "type": "low_confidence_outlier",
                    "severity": "info",
                    "memory_ids": [m.get("memory_id")],
                    "description": f"Approved memory has low confidence ({confidence:.2f})",
                    "details": {"content": self._short(m.get("content", ""))},
                })
        return anomalies

    def detect_quality_confidence_gap(self, memories: List[Dict]) -> List[Dict]:
        """Quality score and confidence strongly disagree - scoring may be broken."""
        anomalies = []
        for m in memories:
            quality = m.get("quality_score", 0.0)
            confidence = m.get("confidence", 0.0)
            gap = abs(quality - confidence)
            if gap >= self.QUALITY_CONFIDENCE_GAP_THRESHOLD:
                anomalies.append({
                    "type": "quality_confidence_gap",
                    "severity": "info",
                    "memory_ids": [m.get("memory_id")],
                    "description": (
                        f"quality_score ({quality:.2f}) and confidence ({confidence:.2f}) "
                        f"disagree by {gap:.2f}"
                    ),
                    "details": {"content": self._short(m.get("content", ""))},
                })
        return anomalies

    def detect_burst_ingestion(self, memories: List[Dict]) -> List[Dict]:
        """Unusually many memories created at the exact same timestamp."""
        anomalies = []
        by_timestamp = defaultdict(list)
        for m in memories:
            ts = m.get("timestamp")
            if ts:
                by_timestamp[ts].append(m)

        for ts, group in by_timestamp.items():
            if len(group) >= self.BURST_INGESTION_MIN_COUNT:
                anomalies.append({
                    "type": "burst_ingestion",
                    "severity": "warning",
                    "memory_ids": [m.get("memory_id") for m in group],
                    "description": (
                        f"{len(group)} memories created at identical timestamp {ts} "
                        "- possible duplicate ingestion or loop bug"
                    ),
                    "details": {"count": len(group), "timestamp": ts},
                })
        return anomalies

    def detect_broken_supersession(self, memories: List[Dict]) -> List[Dict]:
        """superseded_by points at a memory_id that doesn't exist in the store."""
        anomalies = []
        known_ids = {m.get("memory_id") for m in memories}

        for m in memories:
            target = m.get("superseded_by")
            if target and target not in known_ids:
                anomalies.append({
                    "type": "broken_supersession",
                    "severity": "critical",
                    "memory_ids": [m.get("memory_id")],
                    "description": f"superseded_by references missing memory_id '{target}'",
                    "details": {"content": self._short(m.get("content", ""))},
                })
        return anomalies

    def detect_trivial_content(self, memories: List[Dict]) -> List[Dict]:
        """Content too short/empty to carry real meaning."""
        anomalies = []
        for m in memories:
            content = (m.get("content") or "").strip()
            if len(content) < self.TRIVIAL_CONTENT_MIN_LENGTH:
                anomalies.append({
                    "type": "trivial_content",
                    "severity": "info",
                    "memory_ids": [m.get("memory_id")],
                    "description": f"Content is only {len(content)} chars - likely noise",
                    "details": {"content": content},
                })
        return anomalies

    # -- orchestration ------------------------------------------------------

    def detect_all(self, memories: Optional[List[Dict]] = None) -> Dict:
        """Run every detector and return a combined, severity-sorted report."""
        memories = memories if memories is not None else self.load_memories()

        detectors = [
            self.detect_duplicate_content,
            self.detect_stale_open_loops,
            self.detect_low_confidence_outliers,
            self.detect_quality_confidence_gap,
            self.detect_burst_ingestion,
            self.detect_broken_supersession,
            self.detect_trivial_content,
        ]

        all_anomalies = []
        for detector in detectors:
            all_anomalies.extend(detector(memories))

        all_anomalies.sort(key=lambda a: self.SEVERITY_ORDER.get(a["severity"], 99))

        by_severity = defaultdict(int)
        by_type = defaultdict(int)
        for a in all_anomalies:
            by_severity[a["severity"]] += 1
            by_type[a["type"]] += 1

        return {
            "generated_at": datetime.now().isoformat(),
            "total_memories_scanned": len(memories),
            "total_anomalies": len(all_anomalies),
            "by_severity": dict(by_severity),
            "by_type": dict(by_type),
            "anomalies": all_anomalies,
        }

    def to_markdown(self, report: Dict) -> str:
        lines = ["# Anomaly Report", ""]
        lines.append(f"_Generated {report['generated_at']}_")
        lines.append(f"**Scanned:** {report['total_memories_scanned']} memories, "
                      f"**found:** {report['total_anomalies']} anomalies")
        lines.append("")

        if report["by_severity"]:
            severity_summary = ", ".join(
                f"{sev}: {count}" for sev, count in sorted(
                    report["by_severity"].items(),
                    key=lambda kv: self.SEVERITY_ORDER.get(kv[0], 99),
                )
            )
            lines.append(f"**By severity:** {severity_summary}")
            lines.append("")

        icons = {"critical": "🔴", "warning": "🟡", "info": "🔵"}
        for anomaly in report["anomalies"]:
            icon = icons.get(anomaly["severity"], "•")
            lines.append(f"{icon} **[{anomaly['type']}]** {anomaly['description']}")
            for key, value in anomaly.get("details", {}).items():
                lines.append(f"   - {key}: {value}")
            lines.append("")

        if not report["anomalies"]:
            lines.append("No anomalies detected. ✅")

        return "\n".join(lines)


if __name__ == "__main__":
    import argparse

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
