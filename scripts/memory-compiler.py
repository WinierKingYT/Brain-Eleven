#!/usr/bin/env python3
"""
Brain-Eleven Memory Compiler
Transforms Daily notes + Threads into persistent semantic memory

Pipeline:
  Daily.md + Threads.md
    ↓
  Parse sections (IMPORTANT DECISION, LEARNED, OPEN LOOPS)
    ↓
  Extract candidates (Observation, Decision, Lesson, Preference)
    ↓
  Deduplicate & validate
    ↓
  Score by importance
    ↓
  Canonical memory format
    ↓
  Output: candidates.json (ready for mem0)
"""

import json
import re
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, asdict
from typing import List, Dict, Optional
from enum import Enum

# ============================================================================
# Data Models
# ============================================================================

class MemoryType(Enum):
    """Types of memory that can be extracted"""
    OBSERVATION = "observation"    # What happened
    DECISION = "decision"          # What was chosen
    LESSON = "lesson"              # What was learned
    PREFERENCE = "preference"      # What I like/dislike
    OPEN_LOOP = "open_loop"        # Unresolved work


@dataclass
class MemoryCandidate:
    """A potential memory entry"""
    type: str
    content: str
    confidence: float          # 0.0 - 1.0
    source: str               # "daily", "thread", "decision"
    timestamp: str            # ISO format
    related_notes: List[str]  # Hamle notes references
    section: Optional[str]    # Section in source document
    source_id: str = ""       # Canonical location (daily:YYYY-MM-DD:type:idx)

    def to_dict(self):
        return asdict(self)


class MemoryCompiler:
    """Main compiler: Daily → Memory"""

    def __init__(self, vault_path: str):
        self.vault_path = Path(vault_path)
        self.companion_path = self.vault_path / "🔮 Companion"
        self.decisions_path = self.vault_path / "🗂️ Proje Notları/Kararlar"

        self.candidates: List[MemoryCandidate] = []
        self.timestamp = datetime.now().isoformat()

    # ========================================================================
    # EXTRACTION: Daily → Candidates
    # ========================================================================

    def extract_from_daily(self) -> int:
        """Parse Daily.md with date awareness (handles multiple daily entries)"""

        daily_file = self.companion_path / "Daily.md"
        if not daily_file.exists():
            print("⚠️  Daily.md not found")
            return 0

        with open(daily_file, 'r', encoding='utf-8') as f:
            content = f.read()

        # Split by date entries: # Daily Notes - YYYY-MM-DD
        import re
        date_pattern = r'^# Daily Notes - (\d{4}-\d{2}-\d{2})'
        date_entries = re.split(date_pattern, content, flags=re.MULTILINE)

        # Process each date's sections
        # Structure: [text_before_first_date, date1, content1, date2, content2, ...]
        for i in range(1, len(date_entries), 2):
            if i + 1 < len(date_entries):
                date_str = date_entries[i]  # YYYY-MM-DD
                date_content = date_entries[i + 1]

                # Track section counts per date for source_id
                section_counts = {}

                # Parse sections for THIS date only
                sections = self._parse_sections_for_date(date_content)

                for section_name, section_text in sections.items():
                    if not section_text.strip():
                        continue

                    # Increment section count for source_id
                    section_counts[section_name] = section_counts.get(section_name, 0) + 1
                    idx = section_counts[section_name] - 1

                    # Extract based on section type (pass date for source_id generation)
                    if section_name == "IMPORTANT DECISION":
                        self._extract_decision(section_text, "daily", date_str, idx)

                    elif section_name == "LEARNED":
                        self._extract_lesson(section_text, "daily", date_str, idx)

                    elif section_name == "OPEN LOOPS":
                        self._extract_open_loop(section_text, "daily", date_str, idx)

                    elif section_name in ["TODAY", "ACTIONS", "PROGRESS"]:
                        self._extract_observation(section_text, "daily", date_str, idx)

        return len(self.candidates)

    def _extract_decision(self, text: str, source: str, date_str: str = "", idx: int = 0):
        """Extract decision candidates"""

        # Clean text
        text = text.strip()
        if len(text) < 20:
            return

        # Find related Hamle notes
        related = self._find_related_notes(text)

        # Generate source_id with date
        source_id = f"daily:{date_str}:decision:{idx}" if date_str else f"daily:decision:{idx}"

        candidate = MemoryCandidate(
            type=MemoryType.DECISION.value,
            content=text,
            confidence=0.95,  # Decisions are high-confidence
            source=source,
            timestamp=self.timestamp,
            related_notes=related,
            section="IMPORTANT DECISION",
            source_id=source_id
        )

        self.candidates.append(candidate)

    def _extract_lesson(self, text: str, source: str, date_str: str = "", idx: int = 0):
        """Extract lesson candidates"""

        text = text.strip()
        if len(text) < 20:
            return

        related = self._find_related_notes(text)

        # Generate source_id with date
        source_id = f"daily:{date_str}:lesson:{idx}" if date_str else f"daily:lesson:{idx}"

        candidate = MemoryCandidate(
            type=MemoryType.LESSON.value,
            content=text,
            confidence=0.85,
            source=source,
            timestamp=self.timestamp,
            related_notes=related,
            section="LEARNED",
            source_id=source_id
        )

        self.candidates.append(candidate)

    def _extract_open_loop(self, text: str, source: str, date_str: str = "", idx: int = 0):
        """Extract unresolved work"""

        # Parse checkbox items
        lines = text.strip().split('\n')
        item_idx = 0

        for line in lines:
            line = line.strip()
            if not line or line.startswith('#'):
                continue

            # Extract task description (remove checkbox)
            task = re.sub(r'^\s*[-•]\s*\[.\]\s*', '', line).strip()

            if not task:
                continue

            # Generate source_id with date and item index
            source_id = f"daily:{date_str}:open_loop:{idx}:{item_idx}" if date_str else f"daily:open_loop:{idx}:{item_idx}"

            candidate = MemoryCandidate(
                type=MemoryType.OPEN_LOOP.value,
                content=task,
                confidence=0.90,
                source=source,
                timestamp=self.timestamp,
                related_notes=[],
                section="OPEN LOOPS",
                source_id=source_id
            )

            self.candidates.append(candidate)
            item_idx += 1

    def _extract_observation(self, text: str, source: str, date_str: str = "", idx: int = 0):
        """Extract what happened (lower confidence)"""

        # Split into sentences
        sentences = re.split(r'[.!?]+', text)
        sent_idx = 0

        for sentence in sentences:
            sentence = sentence.strip()
            if len(sentence) < 10:
                continue

            # Observations are lower confidence (they're contextual)
            related = self._find_related_notes(sentence)

            # Generate source_id with date and sentence index
            source_id = f"daily:{date_str}:observation:{idx}:{sent_idx}" if date_str else f"daily:observation:{idx}:{sent_idx}"

            candidate = MemoryCandidate(
                type=MemoryType.OBSERVATION.value,
                content=sentence,
                confidence=0.65,
                source=source,
                timestamp=self.timestamp,
                related_notes=related,
                section="OBSERVATION",
                source_id=source_id
            )

            self.candidates.append(candidate)
            sent_idx += 1

    # ========================================================================
    # DEDUPLICATION: Remove near-duplicates
    # ========================================================================

    def deduplicate(self) -> int:
        """Remove duplicate candidates using simple heuristics"""

        before = len(self.candidates)

        # Group by semantic similarity
        seen = {}
        deduplicated = []

        for candidate in self.candidates:
            # Create a simplified hash (first 50 chars + type)
            sim_hash = f"{candidate.type}:{candidate.content[:50]}"

            if sim_hash not in seen:
                deduplicated.append(candidate)
                seen[sim_hash] = candidate
            else:
                # Merge: keep higher confidence
                existing = seen[sim_hash]
                if candidate.confidence > existing.confidence:
                    deduplicated[deduplicated.index(existing)] = candidate

        self.candidates = deduplicated
        after = len(self.candidates)

        return before - after  # Return number removed

    # ========================================================================
    # VALIDATION: Quality gate
    # ========================================================================

    def validate_and_score(self) -> int:
        """Quality gate: filter low-quality candidates"""

        before = len(self.candidates)
        validated = []

        for candidate in self.candidates:
            # Check 1: Minimum length
            if len(candidate.content.strip()) < 15:
                continue

            # Check 2: Not filler text
            if self._is_filler(candidate.content):
                continue

            # Check 3: Type-specific confidence adjustments
            if candidate.type == MemoryType.DECISION.value:
                # Reduce confidence if tentative ("might", "should consider")
                if any(word in candidate.content.lower() for word in ["might", "maybe", "perhaps", "consider"]):
                    candidate.confidence *= 0.8

            if candidate.type == MemoryType.OBSERVATION.value:
                # Boost if it relates to decisions/lessons
                if candidate.related_notes:
                    candidate.confidence += 0.1

            # Check 4: Confidence threshold
            if candidate.confidence > 0.5:
                validated.append(candidate)

        self.candidates = validated
        after = len(self.candidates)

        return before - after  # Return number removed

    # ========================================================================
    # UTILITIES
    # ========================================================================

    def _parse_sections_for_date(self, content: str) -> Dict[str, str]:
        """Parse markdown sections for a single date (## SECTION_NAME)"""

        sections = {}
        current_section = None
        current_text = []

        for line in content.split('\n'):
            if line.startswith('## '):
                # Save previous section
                if current_section:
                    sections[current_section] = '\n'.join(current_text).strip()

                # Start new section
                current_section = line[3:].strip()
                current_text = []
            else:
                if current_section:
                    current_text.append(line)

        # Save last section
        if current_section:
            sections[current_section] = '\n'.join(current_text).strip()

        return sections

    def _find_related_notes(self, text: str) -> List[str]:
        """Find related Hamle decision notes"""

        related = []

        # Simple pattern matching: hamleN-xxx-descriptive-name
        hamle_pattern = r'hamle\d+-\w+-[\w-]+'
        matches = re.findall(hamle_pattern, text, re.IGNORECASE)

        # Also check if keywords match Hamle topics
        keywords = {
            'backend': 'hamle5-backend',
            'frontend': 'hamle5-frontend',
            'performance': 'hamle5-performance',
            'security': 'hamle6-security',
            'api': 'hamle6-api',
            'testing': 'hamle6-testing',
            'event': 'hamle7-messaging',
            'data': 'hamle7-data',
            'search': 'hamle7-search',
            'mobile': 'hamle7-mobile',
            'ml': 'hamle7-ml'
        }

        for keyword, prefix in keywords.items():
            if keyword.lower() in text.lower():
                related.append(prefix)

        return list(set(matches + related))[:5]  # Limit to 5

    def _is_filler(self, text: str) -> bool:
        """Check if text is likely filler/boilerplate"""

        filler_patterns = [
            r'^\s*\.\.\.\s*$',
            r'^TBD$',
            r'^(todo|wip|draft)$',
            r'^working on it',
            r'^need to (think about|review|check)',
        ]

        for pattern in filler_patterns:
            if re.match(pattern, text, re.IGNORECASE):
                return True

        return False

    # ========================================================================
    # COMPILATION PIPELINE
    # ========================================================================

    def compile(self) -> Dict:
        """Execute full compilation pipeline"""

        print("📊 Brain-Eleven Memory Compiler")
        print("=" * 50)

        # Step 1: Extract
        print("\n1. Extracting from Daily.md...")
        extracted = self.extract_from_daily()
        print(f"   → {extracted} candidates extracted")

        # Step 2: Deduplicate
        print("\n2. Deduplicating...")
        removed_dups = self.deduplicate()
        print(f"   → {removed_dups} duplicates removed ({len(self.candidates)} remaining)")

        # Step 3: Validate & Score
        print("\n3. Validating & scoring...")
        removed_invalid = self.validate_and_score()
        print(f"   → {removed_invalid} low-quality removed ({len(self.candidates)} valid)")

        # Step 4: Organize by type
        print("\n4. Organizing by type...")
        by_type = {}
        for candidate in self.candidates:
            typ = candidate.type
            if typ not in by_type:
                by_type[typ] = []
            by_type[typ].append(candidate)

        for typ, items in by_type.items():
            print(f"   • {typ.upper()}: {len(items)}")

        # Output
        output = {
            "compiled_at": self.timestamp,
            "summary": {
                "total_candidates": len(self.candidates),
                "by_type": {k: len(v) for k, v in by_type.items()}
            },
            "candidates": [c.to_dict() for c in self.candidates],
            "next_step": "Send candidates.json to mem0 or review in Obsidian"
        }

        print("\n" + "=" * 50)
        print(f"✅ Compilation complete")
        print(f"   Total: {len(self.candidates)} valid memory candidates")
        print(f"\nReady for: mem0 ingestion or Obsidian review")

        return output

    def save_output(self, output_file: str = None) -> str:
        """Save compilation output to JSON"""

        if output_file is None:
            output_file = str(self.vault_path / ".claude/compiled-memory.json")

        output = self.compile()

        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(output, f, indent=2, ensure_ascii=False)

        print(f"\n📁 Saved to: {output_file}")
        return output_file


# ============================================================================
# CLI
# ============================================================================

if __name__ == "__main__":
    import sys

    vault_path = Path.home() / "Documents/Brain-Eleven"

    compiler = MemoryCompiler(str(vault_path))
    output_file = compiler.save_output()

    print(f"\n🎯 Next steps:")
    print(f"   1. Review: {output_file}")
    print(f"   2. When mem0 ready: sync candidates to mem0")
    print(f"   3. Update Obsidian with validated decisions")
