#!/usr/bin/env python3
"""
Brain-Eleven v3 - Auto-Summarizer (Phase 10A)

Produces a digest of the memory store without requiring an LLM or real
embeddings: memories here are already short atomic facts (decisions,
lessons, observations, open loops), so "summarization" means picking the
most important, non-redundant entries per type and per day - not
compressing long prose.

Deliberately independent of embedding-generator.py's OpenAI dependency:
dedup uses token-level Jaccard similarity, ranking uses the
quality_score/confidence already computed by memory-validator.py during
the validation pipeline. Works identically whether embeddings are real
or fallback.
"""

import json
import re
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from collections import defaultdict

from logging_config import setup_logging

logger = setup_logging(__name__)

STOPWORDS = {
    "the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "with",
    "is", "are", "was", "were", "be", "been", "this", "that", "it", "as",
    "at", "by", "from", "we", "our",
}


def tokenize(text: str) -> set:
    """Lowercase word tokens, punctuation stripped, stopwords removed."""
    words = re.findall(r"[a-zA-Z0-9']+", text.lower())
    return {w for w in words if w not in STOPWORDS and len(w) > 1}


def jaccard_similarity(a: str, b: str) -> float:
    """Token overlap ratio between two strings, 0.0-1.0."""
    tokens_a, tokens_b = tokenize(a), tokenize(b)
    if not tokens_a or not tokens_b:
        return 0.0
    intersection = len(tokens_a & tokens_b)
    union = len(tokens_a | tokens_b)
    return intersection / union if union else 0.0


class MemorySummarizer:
    """Builds digests over the validated memory store."""

    DUPLICATE_THRESHOLD = 0.6  # jaccard similarity above this = "same idea"

    def __init__(self, vault_path: str = "."):
        self.vault_path = Path(vault_path)
        self.memory_file = self.vault_path / ".claude" / "validated-memory.json"

    def load_memories(self, statuses: Optional[List[str]] = None) -> List[Dict]:
        """Load memories, optionally filtered by status (default: all)."""
        if not self.memory_file.exists():
            logger.warning(f"No memory file at {self.memory_file}")
            return []

        with open(self.memory_file, encoding="utf-8") as f:
            data = json.load(f)

        memories = data.get("validated_memory", [])
        if statuses:
            memories = [m for m in memories if m.get("status", "active") in statuses]
        return memories

    @staticmethod
    def extract_date(memory: Dict) -> Optional[str]:
        """Pull a YYYY-MM-DD date from source_id ('daily:2026-08-28:...') or timestamp."""
        source_id = memory.get("source_id", "")
        parts = source_id.split(":")
        if len(parts) >= 2 and re.match(r"^\d{4}-\d{2}-\d{2}$", parts[1]):
            return parts[1]

        timestamp = memory.get("timestamp", "")
        if timestamp:
            try:
                return datetime.fromisoformat(timestamp).strftime("%Y-%m-%d")
            except ValueError:
                return None
        return None

    @staticmethod
    def rank_score(memory: Dict) -> float:
        """Composite importance score: quality (60%) + confidence (40%)."""
        quality = memory.get("quality_score", 0.0)
        confidence = memory.get("confidence", 0.0)
        return quality * 0.6 + confidence * 0.4

    def dedupe_similar(self, memories: List[Dict]) -> List[Dict]:
        """
        Collapse near-duplicate memories (by content token overlap),
        keeping the highest-ranked representative of each cluster.
        """
        if not memories:
            return []

        ranked = sorted(memories, key=self.rank_score, reverse=True)
        kept: List[Dict] = []

        for candidate in ranked:
            content = candidate.get("content", "")
            is_duplicate = any(
                jaccard_similarity(content, k.get("content", "")) >= self.DUPLICATE_THRESHOLD
                for k in kept
            )
            if not is_duplicate:
                kept.append(candidate)

        return kept

    def generate_type_digest(self, memories: List[Dict], top_n: int = 5) -> Dict[str, List[Dict]]:
        """Group by type, dedupe, and take the top N by rank per type."""
        by_type = defaultdict(list)
        for m in memories:
            by_type[m.get("type", "unknown")].append(m)

        digest = {}
        for mem_type, items in by_type.items():
            deduped = self.dedupe_similar(items)
            ranked = sorted(deduped, key=self.rank_score, reverse=True)
            digest[mem_type] = ranked[:top_n]

        return digest

    def generate_digest(
        self,
        days: Optional[int] = None,
        top_n_per_type: int = 5,
        statuses: Optional[List[str]] = None,
    ) -> Dict:
        """
        Build a full digest.

        Args:
            days: only include memories from the last N days (None = all time)
            top_n_per_type: max entries kept per memory type after dedup
            statuses: filter by status (default: active + resolved, excludes superseded)
        """
        statuses = statuses or ["active", "resolved"]
        memories = self.load_memories(statuses=statuses)

        if days is not None:
            cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
            memories = [m for m in memories if (self.extract_date(m) or "") >= cutoff]

        by_type_digest = self.generate_type_digest(memories, top_n=top_n_per_type)

        dates = sorted({d for m in memories if (d := self.extract_date(m))})

        return {
            "generated_at": datetime.now().isoformat(),
            "period_days": days,
            "date_range": {"from": dates[0] if dates else None, "to": dates[-1] if dates else None},
            "total_memories_considered": len(memories),
            "total_after_dedup": sum(len(v) for v in by_type_digest.values()),
            "by_type": {
                mem_type: [
                    {
                        "memory_id": m.get("memory_id"),
                        "content": m.get("content"),
                        "confidence": m.get("confidence"),
                        "quality_score": m.get("quality_score"),
                        "status": m.get("status"),
                        "date": self.extract_date(m),
                    }
                    for m in items
                ]
                for mem_type, items in by_type_digest.items()
            },
        }

    def to_markdown(self, digest: Dict) -> str:
        """Render a digest dict as a readable Markdown report."""
        lines = ["# Memory Digest", ""]

        period = f"last {digest['period_days']} days" if digest["period_days"] else "all time"
        lines.append(f"_Generated {digest['generated_at']} - {period}_")
        lines.append("")

        date_range = digest["date_range"]
        if date_range["from"]:
            lines.append(f"**Date range:** {date_range['from']} → {date_range['to']}")
        lines.append(f"**Considered:** {digest['total_memories_considered']} memories "
                      f"→ **{digest['total_after_dedup']}** after dedup")
        lines.append("")

        type_order = ["decision", "lesson", "open_loop", "observation"]
        types_present = list(digest["by_type"].keys())
        ordered_types = [t for t in type_order if t in types_present]
        ordered_types += [t for t in types_present if t not in ordered_types]

        for mem_type in ordered_types:
            items = digest["by_type"][mem_type]
            if not items:
                continue
            lines.append(f"## {mem_type.replace('_', ' ').title()} ({len(items)})")
            lines.append("")
            for item in items:
                date = item["date"] or "?"
                lines.append(f"- **[{date}]** {item['content']} "
                              f"_(confidence: {item['confidence']:.2f}, "
                              f"quality: {item['quality_score']:.2f})_")
            lines.append("")

        return "\n".join(lines)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Generate a Brain-Eleven memory digest")
    parser.add_argument("--vault", default=".", help="Path to vault root")
    parser.add_argument("--days", type=int, default=None, help="Only include last N days")
    parser.add_argument("--top-n", type=int, default=5, help="Max entries per type")
    parser.add_argument("--json", action="store_true", help="Output raw JSON instead of Markdown")
    args = parser.parse_args()

    summarizer = MemorySummarizer(vault_path=args.vault)
    digest = summarizer.generate_digest(days=args.days, top_n_per_type=args.top_n)

    if args.json:
        print(json.dumps(digest, indent=2, ensure_ascii=False))
    else:
        print(summarizer.to_markdown(digest))
