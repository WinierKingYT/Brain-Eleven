#!/usr/bin/env python3
"""
Brain-Eleven Memory Validator
Quality gate before persistence: conflict detection, uniqueness, scoring

Pipeline:
  candidates.json (from memory-compiler)
    ↓
  Conflict detection (contradictions between candidates)
    ↓
  Uniqueness check (not already stored)
    ↓
  Quality scoring (novelty, relevance, importance)
    ↓
  Canonical form normalization
    ↓
  Output: validated-memory.json (ready for Obsidian + mem0)
"""

import json
import re
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, asdict
from typing import List, Dict, Optional, Tuple
from enum import Enum

# ============================================================================
# Data Models
# ============================================================================

@dataclass
class ValidationIssue:
    """Problems found during validation"""
    type: str  # "contradiction", "duplicate", "low_quality", "novelty"
    severity: str  # "error", "warning", "info"
    candidate_ids: List[int]  # Which candidates are affected
    description: str
    recommendation: str


@dataclass
class ValidatedMemory:
    """Memory after passing validation gate"""
    id: int
    type: str
    content: str
    confidence: float
    source: str
    timestamp: str
    related_notes: List[str]
    section: str

    # Validation results
    issues: List[ValidationIssue]
    quality_score: float  # 0.0 - 1.0 (after all adjustments)
    novelty: float  # Is this new knowledge?
    is_approved: bool  # Passes validation gate?

    # Lifecycle (Phase 4+): Prevents memory poisoning
    status: str = "active"  # active, resolved, superseded
    resolved_at: str = ""  # ISO timestamp when resolved
    resolved_by: str = ""  # git commit hash or reference

    def to_dict(self):
        return {
            **asdict(self),
            "issues": [asdict(i) for i in self.issues]
        }


class MemoryValidator:
    """Validates candidates before persistence"""

    def __init__(self, vault_path: str):
        self.vault_path = Path(vault_path)
        self.compiled_json = self.vault_path / ".claude/compiled-memory.json"
        self.existing_memory = self._load_existing_memory()
        self.candidates = []
        self.validated = []

    # ========================================================================
    # LOAD EXISTING MEMORY
    # ========================================================================

    def _load_existing_memory(self) -> Dict[str, List[str]]:
        """Load existing memory from Obsidian notes + prior compilations"""

        existing = {
            "observations": [],
            "decisions": [],
            "lessons": [],
            "open_loops": []
        }

        # Read Last Session.md
        last_session_file = self.vault_path / "🔮 Companion/Last Session.md"
        if last_session_file.exists():
            with open(last_session_file, 'r', encoding='utf-8') as f:
                content = f.read()
                # Extract stored content (simplified)
                existing["decisions"].extend(self._extract_text_snippets(content, "Decisions"))
                existing["lessons"].extend(self._extract_text_snippets(content, "Lessons"))

        # Read prior compilations
        prior_compile = self.vault_path / ".claude/compiled-memory-prior.json"
        if prior_compile.exists():
            with open(prior_compile, 'r', encoding='utf-8') as f:
                prior = json.load(f)
                for candidate in prior.get("candidates", []):
                    typ = candidate["type"]
                    if typ in existing:
                        existing[typ].append(candidate["content"])

        return existing

    def _extract_text_snippets(self, text: str, section: str) -> List[str]:
        """Extract snippets from markdown section"""
        pattern = f"## {section}(.*?)(?=##|$)"
        match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
        if match:
            section_text = match.group(1)
            # Split into sentences/items
            items = [s.strip() for s in section_text.split('\n') if s.strip() and not s.startswith('#')]
            return items
        return []

    # ========================================================================
    # LOAD CANDIDATES
    # ========================================================================

    def load_candidates(self):
        """Load from compiled-memory.json"""
        if not self.compiled_json.exists():
            print("⚠️  compiled-memory.json not found")
            return 0

        with open(self.compiled_json, 'r', encoding='utf-8') as f:
            data = json.load(f)

        # Convert to ValidatedMemory objects
        for i, candidate in enumerate(data.get("candidates", [])):
            validated = ValidatedMemory(
                id=i,
                type=candidate["type"],
                content=candidate["content"],
                confidence=candidate["confidence"],
                source=candidate["source"],
                timestamp=candidate["timestamp"],
                related_notes=candidate.get("related_notes", []),
                section=candidate.get("section", ""),
                issues=[],
                quality_score=candidate["confidence"],  # Start with compiler confidence
                novelty=0.5,  # To be calculated
                is_approved=False
            )
            self.candidates.append(validated)

        return len(self.candidates)

    # ========================================================================
    # VALIDATION: Conflict Detection
    # ========================================================================

    def detect_conflicts(self):
        """Find contradictions between candidates"""

        print("\n🔍 Detecting conflicts...")
        conflicts = []

        # Compare all pairs of decisions
        decisions = [c for c in self.candidates if c.type == "decision"]

        for i, d1 in enumerate(decisions):
            for d2 in decisions[i+1:]:
                conflict = self._check_contradiction(d1, d2)
                if conflict:
                    conflicts.append(conflict)
                    print(f"  ⚠️  CONFLICT between decision {d1.id} and {d2.id}")
                    print(f"      {d1.content[:60]}...")
                    print(f"      vs")
                    print(f"      {d2.content[:60]}...")

        return conflicts

    def _check_contradiction(self, m1: ValidatedMemory, m2: ValidatedMemory) -> Optional[ValidationIssue]:
        """Check if two memories contradict"""

        content1 = m1.content.lower()
        content2 = m2.content.lower()

        # Pattern-based detection
        contradictions = [
            ("use", "don't use"),
            ("should", "shouldn't"),
            ("will", "won't"),
            ("yes", "no"),
            ("enable", "disable"),
            ("proceed", "abort"),
            ("phased", "monolithic"),
        ]

        for positive, negative in contradictions:
            if positive in content1 and negative in content2:
                return ValidationIssue(
                    type="contradiction",
                    severity="warning",
                    candidate_ids=[m1.id, m2.id],
                    description=f"Decision {m1.id} and {m2.id} may contradict on '{positive}' vs '{negative}'",
                    recommendation="Review both decisions; keep the newer one or combine them"
                )

            if negative in content1 and positive in content2:
                return ValidationIssue(
                    type="contradiction",
                    severity="warning",
                    candidate_ids=[m1.id, m2.id],
                    description=f"Decision {m1.id} and {m2.id} may contradict on '{positive}' vs '{negative}'",
                    recommendation="Review both decisions; keep the newer one or combine them"
                )

        return None

    # ========================================================================
    # VALIDATION: Uniqueness
    # ========================================================================

    def check_uniqueness(self):
        """Detect if memory already exists"""

        print("\n🔄 Checking uniqueness...")
        duplicates = []

        for candidate in self.candidates:
            # Check against existing memory
            existing_list = self.existing_memory.get(candidate.type + "s", [])

            for existing in existing_list:
                similarity = self._similarity_score(candidate.content, existing)

                if similarity > 0.85:  # Very similar = likely duplicate
                    issue = ValidationIssue(
                        type="duplicate",
                        severity="info",
                        candidate_ids=[candidate.id],
                        description=f"Similar to existing {candidate.type}: '{existing[:50]}...'",
                        recommendation="Skip or merge with existing memory"
                    )
                    candidate.issues.append(issue)
                    duplicates.append(issue)
                    print(f"  ℹ️  Similarity found for candidate {candidate.id} (score: {similarity:.2f})")

        return duplicates

    def _similarity_score(self, text1: str, text2: str) -> float:
        """Simple similarity (shared words / total unique words)"""
        words1 = set(text1.lower().split())
        words2 = set(text2.lower().split())

        if not words1 or not words2:
            return 0.0

        intersection = len(words1 & words2)
        union = len(words1 | words2)

        return intersection / union if union > 0 else 0.0

    # ========================================================================
    # VALIDATION: Quality Scoring
    # ========================================================================

    def score_quality(self):
        """Calculate final quality score"""

        print("\n⭐ Scoring quality...")

        for candidate in self.candidates:
            # Start with compiler confidence
            score = candidate.confidence

            # Novelty adjustment (is this new knowledge?)
            novelty = self._calculate_novelty(candidate)
            candidate.novelty = novelty
            score += (novelty * 0.2)  # Novelty contributes 20%

            # Type-specific adjustments
            if candidate.type == "decision":
                score += 0.1  # Decisions valued higher

            elif candidate.type == "lesson":
                score += 0.05  # Lessons also valued

            elif candidate.type == "observation":
                # Observations decay faster (older = less valuable)
                days_old = self._days_since_timestamp(candidate.timestamp)
                decay = 1.0 - (days_old * 0.05)  # 5% decay per day
                score *= decay

            # Penalty for issues
            for issue in candidate.issues:
                if issue.severity == "error":
                    score -= 0.3
                elif issue.severity == "warning":
                    score -= 0.1

            # Clamp to 0-1
            candidate.quality_score = max(0.0, min(1.0, score))

            # Approval threshold
            candidate.is_approved = candidate.quality_score > 0.55

            print(f"  Candidate {candidate.id} ({candidate.type}): {candidate.quality_score:.2f} {'✅' if candidate.is_approved else '❌'}")

    def _calculate_novelty(self, candidate: ValidatedMemory) -> float:
        """How new is this knowledge?"""
        # Keywords indicating high novelty
        high_novelty_words = ["new", "discovered", "realized", "learned", "changed", "decided", "pivoted"]

        content_lower = candidate.content.lower()
        novelty = 0.5  # Baseline

        if any(word in content_lower for word in high_novelty_words):
            novelty = 0.9

        return novelty

    def _days_since_timestamp(self, timestamp: str) -> int:
        """Calculate days since timestamp"""
        try:
            dt = datetime.fromisoformat(timestamp)
            now = datetime.now()
            delta = now - dt
            return delta.days
        except:
            return 0

    # ========================================================================
    # OUTPUT
    # ========================================================================

    def validate_all(self) -> Dict:
        """Execute full validation pipeline"""

        print("📋 Brain-Eleven Memory Validator")
        print("=" * 50)

        # Load
        print("\n1. Loading candidates...")
        loaded = self.load_candidates()
        print(f"   → {loaded} candidates loaded")

        # Detect conflicts
        print("\n2. Detecting conflicts...")
        conflicts = self.detect_conflicts()
        for candidate in self.candidates:
            # Add conflicts to candidate issues
            for conflict in conflicts:
                if candidate.id in conflict.candidate_ids:
                    candidate.issues.append(conflict)
        print(f"   → {len(conflicts)} conflicts found")

        # Check uniqueness
        print("\n3. Checking uniqueness...")
        duplicates = self.check_uniqueness()
        print(f"   → {len(duplicates)} duplicates/similar found")

        # Score quality
        print("\n4. Scoring quality...")
        self.score_quality()

        # Summary
        self.validated = [c for c in self.candidates if c.is_approved]

        print("\n" + "=" * 50)
        print(f"✅ Validation complete")
        print(f"   Approved: {len(self.validated)}/{len(self.candidates)}")
        print(f"   Confidence: {sum(c.quality_score for c in self.validated) / len(self.validated) if self.validated else 0:.2f} avg")

        # Build output
        output = {
            "validated_at": datetime.now().isoformat(),
            "summary": {
                "total_candidates": len(self.candidates),
                "approved": len(self.validated),
                "rejected": len(self.candidates) - len(self.validated),
                "conflicts_found": len(conflicts),
                "duplicates_found": len(duplicates),
            },
            "validated_memory": [m.to_dict() for m in self.validated],
            "rejected_memory": [m.to_dict() for m in self.candidates if not m.is_approved],
            "next_step": "Import validated_memory to Obsidian + sync to mem0 when ready"
        }

        return output

    def save_output(self, output_file: str = None) -> str:
        """Save validation results"""

        if output_file is None:
            output_file = str(self.vault_path / ".claude/validated-memory.json")

        output = self.validate_all()

        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(output, f, indent=2, ensure_ascii=False)

        print(f"\n📁 Saved to: {output_file}")

        # Also save prior compilation for next validation
        prior_file = str(self.vault_path / ".claude/compiled-memory-prior.json")
        with open(prior_file, 'w', encoding='utf-8') as f:
            json.dump(
                {"candidates": [c.to_dict() for c in self.candidates]},
                f,
                indent=2,
                ensure_ascii=False
            )

        return output_file


# ============================================================================
# CLI
# ============================================================================

if __name__ == "__main__":
    import sys

    vault_path = Path.home() / "Documents/Brain-Eleven"

    validator = MemoryValidator(str(vault_path))
    output_file = validator.save_output()

    print(f"\n🎯 Next steps:")
    print(f"   1. Review: {output_file}")
    print(f"   2. Approved candidates: ready for Obsidian")
    print(f"   3. Rejected candidates: needs revision")
    print(f"   4. When mem0 ready: sync approved_memory")
