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
from dataclasses import dataclass, asdict, field
from typing import List, Dict, Optional, Tuple
from enum import Enum

from memory_scope import (
    GLOBAL_SCOPE,
    fingerprint_aliases,
    infer_memory_scope,
    resolve_capture_scope,
    scoped_fingerprint,
)
from memory_store import MemoryStore, no_change
from capture_safety import evaluate_capture, require_safe_capture

try:
    from ulid import ULID
except ImportError:
    # Fallback: use UUID if ULID not available
    from uuid import uuid4
    class ULID:
        def __init__(self):
            self.value = str(uuid4())[:20]
        def __str__(self):
            return self.value

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
    # IDENTITY (Phase 5)
    memory_id: str = field(default_factory=lambda: str(ULID()))  # Immutable ULID
    id: int = -1  # Deprecated: array index (kept for backward compat)
    source_id: str = ""  # Canonical source anchor (daily:date:section:n)

    # CONTENT
    type: str = ""
    content: str = ""
    confidence: float = 0.0
    source: str = ""
    timestamp: str = ""
    related_notes: List[str] = field(default_factory=list)
    section: str = ""

    # VALIDATION
    issues: List[ValidationIssue] = field(default_factory=list)
    quality_score: float = 0.0
    novelty: float = 0.0
    is_approved: bool = False

    # LIFECYCLE (Phase 5: rich object instead of flat fields)
    status: str = "active"  # active, resolved, superseded
    resolved_at: str = ""
    resolved_by: str = ""
    resolution_note: str = ""  # Why was it resolved?
    superseded_by: str = ""  # ULID of memory that superseded this one
    supersession_note: str = ""  # Why was it superseded?
    dedup_fingerprint: str = ""  # SHA256 for dedup
    # Scope-aware provenance. ``project`` is a display label; ``project_id``
    # is the opaque namespace key. Absolute paths are never persisted.
    scope: str = GLOBAL_SCOPE
    project: str = ""
    project_label: str = ""
    project_id: str = ""

    def to_dict(self):
        return {
            **asdict(self),
            "issues": [asdict(i) for i in self.issues]
        }


class MemoryValidator:
    """Validates candidates before persistence"""

    def __init__(self, vault_path: str):
        self.vault_path = Path(vault_path)
        self.store = MemoryStore(self.vault_path)
        self.compiled_json = self.vault_path / ".claude/compiled-memory.json"
        self.validated_json = self.vault_path / ".claude/validated-memory.json"
        self.existing_memory = self._load_existing_memory()
        self.prior_validated = self._load_prior_validated()  # Load long-term memory
        self.candidates = []
        self.validated = []
        self.safety_rejections = []

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

    def _load_prior_validated(self) -> Dict[str, any]:
        """Load existing validated-memory.json (cumulative long-term store)"""
        return self.store.load()

    def _reload_persisted_state(self) -> None:
        """Reload store-dependent state after acquiring the writer lock."""
        self.existing_memory = self._load_existing_memory()
        self.prior_validated = self._load_prior_validated()

    # ========================================================================
    # MERGE: Cumulative Memory Store
    # ========================================================================

    def _canonical_by_fingerprint(self) -> Dict[str, Dict]:
        """
        Map dedup_fingerprint -> the canonical persisted record for that
        content, scanning the ENTIRE validated-memory.json.

        Two things make this the single source of truth for "does this
        content already have a memory_id?":

        1. It reads BOTH validated_memory and rejected_memory. A memory that
           was approved on one run and dropped below the quality threshold on
           the next (e.g. observation time-decay) still keeps its identity -
           without this, the following run mints a brand-new ULID for content
           that already exists in the store.
        2. When a fingerprint already has several records (the historical
           duplicate pairs), it keeps the EARLIEST by timestamp, so new
           candidates always bind to the canonical original rather than to
           whichever duplicate happened to be iterated last.

        Superseded records are skipped - they are explicitly retired identity
        and must not be re-adopted.
        """
        canonical: Dict[str, Dict] = {}
        for bucket in ("validated_memory", "rejected_memory"):
            for mem in self.prior_validated.get(bucket, []):
                fp = mem.get("dedup_fingerprint")
                if mem.get("status") == "superseded":
                    continue
                aliases = []
                if fp:
                    aliases.append(fp)
                if mem.get("content"):
                    scope, _, project_id = infer_memory_scope(mem)
                    current_fp = scoped_fingerprint(
                        mem["content"], scope, project_id, mem.get("type", "")
                    )
                    aliases.append(current_fp)
                    # Legacy records used content-only or scope-only keys.
                    # Keep those aliases only when the stored key is not the
                    # current type-aware key, preventing new cross-type merges.
                    if fp != current_fp:
                        aliases.extend(fingerprint_aliases(
                            mem["content"], mem.get("type", ""), scope, project_id,
                            include_legacy=True,
                        )[1:])
                for alias in aliases:
                    incumbent = canonical.get(alias)
                    if incumbent is None or mem.get("timestamp", "") < incumbent.get("timestamp", ""):
                        canonical[alias] = mem
        return canonical

    def _merge_with_prior(self, new_candidates: List[ValidatedMemory]) -> List[ValidatedMemory]:
        """Merge with fingerprint-based dedup (Phase 5: canonical merge)"""

        prior_memories = self.prior_validated.get("validated_memory", [])

        # Index by memory_id (immutable identity) from the approved store...
        prior_by_id = {}
        for mem in prior_memories:
            mid = mem.get("memory_id")
            if mid:
                prior_by_id[mid] = mem

        # ...and by fingerprint across the WHOLE persisted file (see
        # _canonical_by_fingerprint for why the approved array alone is not
        # enough).
        prior_by_fingerprint = self._canonical_by_fingerprint()

        merged = []
        seen_memory_ids = set()
        # Within-batch dedup: two candidates in the SAME compiled batch can
        # carry identical content (repeated in a daily note, re-emitted by the
        # compiler). Without this they would each get their own fresh ULID.
        batch_id_by_fingerprint: Dict[str, str] = {}

        # Process new candidates
        for new_mem in new_candidates:
            # Check if memory_id already exists (update)
            if new_mem.memory_id in prior_by_id:
                prior = prior_by_id[new_mem.memory_id]
                # Preserve full lifecycle from prior
                new_mem.status = prior.get("status", "active")
                new_mem.resolved_at = prior.get("resolved_at", "")
                new_mem.resolved_by = prior.get("resolved_by", "")
                new_mem.resolution_note = prior.get("resolution_note", "")
                new_mem.scope = prior.get("scope", new_mem.scope)
                new_mem.project = prior.get("project", new_mem.project)
                new_mem.project_label = prior.get("project_label", new_mem.project_label or new_mem.project)
                new_mem.project_id = prior.get("project_id", new_mem.project_id)
                new_mem.superseded_by = prior.get("superseded_by", "")
                new_mem.supersession_note = prior.get("supersession_note", "")

            # Check if fingerprint exists (content unchanged, same memory)
            else:
                prior = next(
                    (
                        prior_by_fingerprint[alias]
                        for alias in fingerprint_aliases(
                            new_mem.content,
                            new_mem.type,
                            new_mem.scope,
                            new_mem.project_id,
                            include_legacy=True,
                        )
                        if alias in prior_by_fingerprint
                    ),
                    None,
                )
            if prior is not None:
                # Use prior's memory_id (stable identity)
                new_mem.memory_id = prior.get("memory_id", new_mem.memory_id)
                legacy_aliases = fingerprint_aliases(
                    new_mem.content,
                    new_mem.type,
                    new_mem.scope,
                    new_mem.project_id,
                    include_legacy=True,
                )[1:]
                if prior.get("dedup_fingerprint") in legacy_aliases:
                    # Preserve a legacy key until the explicit migration runs;
                    # this avoids minting a second identity during a rolling
                    # upgrade of an existing store.
                    new_mem.dedup_fingerprint = prior["dedup_fingerprint"]
                new_mem.status = prior.get("status", "active")
                new_mem.resolved_at = prior.get("resolved_at", "")
                new_mem.resolved_by = prior.get("resolved_by", "")
                new_mem.resolution_note = prior.get("resolution_note", "")
                new_mem.scope = prior.get("scope", new_mem.scope)
                new_mem.project = prior.get("project", new_mem.project)
                new_mem.project_label = prior.get("project_label", new_mem.project_label or new_mem.project)
                new_mem.project_id = prior.get("project_id", new_mem.project_id)
                new_mem.superseded_by = prior.get("superseded_by", "")
                new_mem.supersession_note = prior.get("supersession_note", "")

            # Collapse a repeat of content already seen earlier in this batch
            # onto that same memory_id and drop the duplicate row.
            fp = new_mem.dedup_fingerprint
            if fp and fp in batch_id_by_fingerprint:
                new_mem.memory_id = batch_id_by_fingerprint[fp]
                continue
            if fp:
                batch_id_by_fingerprint[fp] = new_mem.memory_id

            merged.append(new_mem)
            seen_memory_ids.add(new_mem.memory_id)

        # Add prior memories not in new batch (resolved loops, etc)
        for mem in prior_memories:
            mid = mem.get("memory_id")
            if mid not in seen_memory_ids:
                prior_mem = ValidatedMemory(
                    memory_id=mid,
                    id=-1,  # Deprecated
                    source_id=mem.get("source_id", ""),
                    type=mem["type"],
                    content=mem["content"],
                    confidence=mem["confidence"],
                    source=mem["source"],
                    scope=mem.get("scope", infer_memory_scope(mem)[0]),
                    project=mem.get("project", ""),
                    project_label=mem.get("project_label", mem.get("project", "")),
                    project_id=mem.get("project_id", infer_memory_scope(mem)[2]),
                    timestamp=mem["timestamp"],
                    related_notes=mem.get("related_notes", []),
                    section=mem.get("section", ""),
                    issues=[],
                    quality_score=mem["quality_score"],
                    novelty=mem.get("novelty", 0.5),
                    is_approved=mem["is_approved"],
                    status=mem.get("status", "active"),
                    resolved_at=mem.get("resolved_at", ""),
                    resolved_by=mem.get("resolved_by", ""),
                    resolution_note=mem.get("resolution_note", ""),
                    superseded_by=mem.get("superseded_by", ""),
                    supersession_note=mem.get("supersession_note", ""),
                    dedup_fingerprint=mem.get("dedup_fingerprint", "")
                )
                merged.append(prior_mem)

        return merged

    # ========================================================================
    # LOAD CANDIDATES
    # ========================================================================

    def load_candidates(self):
        """Load from compiled-memory.json with immutable IDs"""
        if not self.compiled_json.exists():
            print("⚠️  compiled-memory.json not found")
            return 0

        with open(self.compiled_json, 'r', encoding='utf-8') as f:
            data = json.load(f)

        # Convert to ValidatedMemory objects
        for i, candidate in enumerate(data.get("candidates", [])):
            safety = evaluate_capture(candidate.get("content", ""))
            if not safety.accepted:
                self.safety_rejections.append(safety)
                continue
            # Generate immutable ID and fingerprint
            memory_id = candidate.get("memory_id", str(ULID()))
            scope, project, project_id = resolve_capture_scope(
                scope=candidate.get("scope"),
                project=candidate.get("project", ""),
                project_id=candidate.get("project_id", ""),
            )
            fingerprint = self._compute_fingerprint(
                candidate["content"], scope, project_id, candidate.get("type", "")
            )

            validated = ValidatedMemory(
                memory_id=memory_id,
                id=i,  # Keep for backward compat, deprecated
                source_id=candidate.get("source_id", f"daily:{candidate.get('section', 'unknown')}:{i}"),
                type=candidate["type"],
                content=candidate["content"],
                confidence=candidate["confidence"],
                source=candidate["source"],
                scope=scope,
                project=project,
                project_label=project,
                project_id=project_id,
                timestamp=candidate["timestamp"],
                related_notes=candidate.get("related_notes", []),
                section=candidate.get("section", ""),
                issues=[],
                quality_score=candidate["confidence"],  # Start with compiler confidence
                novelty=0.5,  # To be calculated
                is_approved=False,
                resolution_note=candidate.get("resolution_note", ""),
                superseded_by=candidate.get("superseded_by", ""),
                supersession_note=candidate.get("supersession_note", ""),
                dedup_fingerprint=fingerprint
            )
            self.candidates.append(validated)

        return len(self.candidates)

    def _compute_fingerprint(
        self,
        content: str,
        scope: str = GLOBAL_SCOPE,
        project_id: str = "",
        type_: str = "",
    ) -> str:
        """Compute a type- and scope-aware SHA256 dedup key."""
        return scoped_fingerprint(content, scope, project_id, type_)

    # ========================================================================
    # VALIDATION: Conflict Detection
    # ========================================================================

    def detect_conflicts(self):
        """Find contradictions between candidates (new & prior)"""

        print("\n🔍 Detecting conflicts...")
        conflicts = []

        # Phase 1: Conflicts within new candidates
        decisions = [c for c in self.candidates if c.type == "decision"]

        for i, d1 in enumerate(decisions):
            for d2 in decisions[i+1:]:
                if d1.scope != d2.scope or d1.project_id != d2.project_id:
                    continue
                conflict = self._check_contradiction(d1, d2)
                if conflict:
                    conflicts.append(conflict)
                    print(f"  ⚠️  CONFLICT between decision {d1.id} and {d2.id}")
                    print(f"      {d1.content[:60]}...")
                    print(f"      vs")
                    print(f"      {d2.content[:60]}...")

        # Phase 2: Cross-history conflicts (new candidates vs prior memories)
        prior_decisions = [m for m in self.prior_validated.get("validated_memory", [])
                          if m.get("type") == "decision" and m.get("status") == "active"]

        for new_decision in decisions:
            for prior_decision in prior_decisions:
                prior_scope, _, prior_project_id = infer_memory_scope(prior_decision)
                if new_decision.scope != prior_scope or new_decision.project_id != prior_project_id:
                    continue
                conflict = self._check_contradiction_cross_history(new_decision, prior_decision)
                if conflict:
                    conflicts.append(conflict)
                    print(f"  ⚠️  CROSS-HISTORY CONFLICT: new decision vs prior")
                    print(f"      New: {new_decision.content[:50]}...")
                    print(f"      Prior ({prior_decision['memory_id']}): {prior_decision['content'][:50]}...")

        return conflicts

    def _check_contradiction(self, m1: ValidatedMemory, m2: ValidatedMemory) -> Optional[ValidationIssue]:
        """Check if two new memories contradict"""

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

    def _check_contradiction_cross_history(self, new_mem: ValidatedMemory, prior_mem: Dict) -> Optional[ValidationIssue]:
        """Check if new memory contradicts a prior decision"""

        content_new = new_mem.content.lower()
        content_prior = prior_mem["content"].lower()

        # Pattern-based detection
        contradictions = [
            ("use", "don't use"),
            ("should", "shouldn't"),
            ("will", "won't"),
            ("yes", "no"),
            ("enable", "disable"),
            ("proceed", "abort"),
            ("phased", "monolithic"),
            ("async", "sync"),
            ("distributed", "monolithic"),
            ("microservices", "monolith"),
        ]

        for positive, negative in contradictions:
            if positive in content_new and negative in content_prior:
                return ValidationIssue(
                    type="contradiction",
                    severity="warning",
                    candidate_ids=[new_mem.id],
                    description=f"New decision contradicts prior '{prior_mem['memory_id']}' on '{positive}' vs '{negative}'",
                    recommendation=f"Review and reconcile with prior decision {prior_mem['memory_id']}"
                )

            if negative in content_new and positive in content_prior:
                return ValidationIssue(
                    type="contradiction",
                    severity="warning",
                    candidate_ids=[new_mem.id],
                    description=f"New decision contradicts prior '{prior_mem['memory_id']}' on '{positive}' vs '{negative}'",
                    recommendation=f"Review and reconcile with prior decision {prior_mem['memory_id']}"
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

    def _atomic_write(self, filepath: Path, data: Dict, validate_structure: bool = True) -> bool:
        """Write to temp file, validate, then rename (atomic operation)"""

        import tempfile
        import shutil

        try:
            # Write to temp file in same directory (same filesystem for atomic rename)
            temp_fd, temp_path = tempfile.mkstemp(
                dir=filepath.parent,
                prefix='.tmp_',
                suffix='.json'
            )

            with open(temp_fd, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

            # Validate JSON integrity
            with open(temp_path, 'r', encoding='utf-8') as f:
                validate_data = json.load(f)

            # Check structure if requested
            if validate_structure:
                if not isinstance(validate_data, dict):
                    raise ValueError("Data must be a JSON object")

            # Validation passed - atomic rename
            if filepath.exists():
                backup_path = filepath.with_suffix('.backup.json')
                shutil.copy2(filepath, backup_path)
                print(f"  📋 Backup: {backup_path}")

            shutil.move(temp_path, filepath)
            print(f"✅ Atomically persisted to {filepath}")
            return True

        except Exception as e:
            print(f"❌ Atomic write failed: {e}")
            # Clean up temp file
            try:
                if 'temp_path' in locals() and Path(temp_path).exists():
                    Path(temp_path).unlink()
            except OSError as cleanup_error:
                print(f"⚠️  Could not remove temporary file: {cleanup_error}")
            return False

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

        # Merge with prior validated memory (cumulative store)
        print("\n5. Merging with prior memory...")
        prior_count = len(self.prior_validated.get("validated_memory", []))
        self.candidates = self._merge_with_prior(self.candidates)
        merged_count = len(self.candidates)
        print(f"   → Prior: {prior_count}, New/Updated: {loaded}, Merged: {merged_count}")

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
                "safety_rejected": len(self.safety_rejections),
            },
            "validated_memory": [m.to_dict() for m in self.validated],
            "rejected_memory": [m.to_dict() for m in self.candidates if not m.is_approved],
            "next_step": "Import validated_memory to Obsidian + sync to mem0 when ready"
        }

        return output

    # ========================================================================
    # SINGLE-CANDIDATE PATH (ad-hoc writes from the API / chat, not the
    # batch daily-compile flow). This is the ONLY code path that should
    # append to validated-memory.json outside memory-compiler.py's batch
    # run - it exists so a single new memory still gets a real ULID,
    # fingerprint dedup against the live store, conflict detection, and
    # quality scoring, instead of being raw-appended.
    # ========================================================================

    def validate_single(
        self,
        type_: str,
        content: str,
        confidence: float = 0.7,
        source: str = "api",
        project: str = "",
        scope: Optional[str] = None,
        project_id: str = "",
        project_root: Optional[str] = None,
        registry_path: Optional[str] = None,
    ) -> Tuple["ValidatedMemory", List[ValidationIssue], bool]:
        """
        Validate one ad-hoc candidate through the same fingerprint-dedup,
        conflict-detection, and quality-scoring logic the batch pipeline
        uses - just scoped to a single item instead of a compiled batch.

        Returns (memory, issues, is_new):
        - is_new=False means an existing memory with this exact fingerprint
          was found; `memory` is that existing record (a plain dict from
          validated-memory.json, NOT a fresh ValidatedMemory) and the
          caller must NOT append it again.
        - is_new=True means `memory` is a new ValidatedMemory the caller
          should persist via append_validated().
        """
        require_safe_capture(content)
        scope, project, project_id = resolve_capture_scope(
            scope=scope,
            project=project,
            project_id=project_id,
            project_root=project_root,
            registry_path=registry_path,
        )
        fingerprint = self._compute_fingerprint(content, scope, project_id, type_)

        # Same canonical fingerprint -> memory_id resolver the batch merge
        # uses: scans validated_memory AND rejected_memory across the whole
        # persisted store and returns the earliest record for the fingerprint,
        # so a repeat POST never mints a second ULID for existing content.
        canonical_by_fingerprint = self._canonical_by_fingerprint()
        for alias in fingerprint_aliases(
            content, type_, scope, project_id, include_legacy=True
        ):
            if alias in canonical_by_fingerprint:
                return canonical_by_fingerprint[alias], [], False

        candidate = ValidatedMemory(
            memory_id=str(ULID()),
            id=-1,
            source_id=f"{source}:{datetime.now().isoformat()}",
            type=type_,
            content=content,
            confidence=confidence,
            source=source,
            scope=scope,
            project=project,
            project_label=project,
            project_id=project_id,
            timestamp=datetime.now().isoformat(),
            related_notes=[],
            section=type_.upper(),
            issues=[],
            quality_score=confidence,
            novelty=0.5,
            is_approved=False,
            dedup_fingerprint=fingerprint,
        )

        # detect_conflicts()/score_quality() both operate on self.candidates -
        # scope it to just this one item so cross-checks run against the
        # live prior store rather than a batch that was never loaded here.
        self.candidates = [candidate]
        conflicts = self.detect_conflicts()
        for conflict in conflicts:
            if candidate.id in conflict.candidate_ids:
                candidate.issues.append(conflict)
        self.score_quality()

        return candidate, candidate.issues, True

    def validate_single_and_append(self, **kwargs):
        """Validate and append one candidate in a lost-update-safe transaction."""
        require_safe_capture(kwargs.get("content", ""))

        def mutate(data):
            self.prior_validated = data
            self.existing_memory = self._load_existing_memory()
            candidate, issues, is_new = self.validate_single(**kwargs)
            if not is_new:
                return no_change((candidate, issues, is_new))
            data.setdefault("validated_memory", []).append(candidate.to_dict())
            self.prior_validated = data
            return candidate, issues, is_new

        result, _persisted = self.store.transact(mutate)
        return result

    def _append_validated_unlocked(self, candidate: "ValidatedMemory") -> bool:
        memories = self.prior_validated.get("validated_memory", [])
        memories.append(candidate.to_dict())
        self.prior_validated["validated_memory"] = memories
        return True

    def append_validated(self, candidate: "ValidatedMemory") -> bool:
        """Atomically append one new (already-validated) memory to the store."""
        require_safe_capture(candidate.content)

        def mutate(data):
            self.prior_validated = data
            self.existing_memory = self._load_existing_memory()
            if candidate.dedup_fingerprint in self._canonical_by_fingerprint():
                return no_change(False)
            data.setdefault("validated_memory", []).append(candidate.to_dict())
            return True

        result, _persisted = self.store.transact(mutate)
        return result

    def save_output(self, output_file: str = None, generated_by_run: str = None) -> str:
        """Save validation results with atomic persistence"""

        if output_file is None:
            output_file = str(self.vault_path / ".claude/validated-memory.json")

        output_path = Path(output_file)
        if output_path.resolve() != self.validated_json.resolve():
            self._reload_persisted_state()
            output = self.validate_all()
            if generated_by_run:
                output["last_validated_by_run"] = generated_by_run
            self._atomic_write(output_path, output)
            return output_file

        def mutate(data):
            self.prior_validated = data
            self.existing_memory = self._load_existing_memory()
            output = self.validate_all()
            if generated_by_run:
                output["last_validated_by_run"] = generated_by_run
            data.clear()
            data.update(output)
            return output

        output, _persisted = self.store.transact(mutate)

        # Also save prior compilation for next validation (a derived artifact).
        prior_file = Path(self.vault_path / ".claude/compiled-memory-prior.json")
        prior_output = {
            "compiled_at": output.get("validated_at"),
            "candidates": output.get("validated_memory", []),
            "generated_by_run": generated_by_run,
        }
        self._atomic_write(prior_file, prior_output, validate_structure=False)
        print(f"💾 Also saved prior: {prior_file}")

        return output_file


# ============================================================================
# CLI
# ============================================================================

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Validate Brain-Eleven memory candidates")
    parser.add_argument("--vault", default=str(Path.home() / "Documents/Brain-Eleven"))
    parser.add_argument("--generated-by-run", default=None)
    args = parser.parse_args()

    validator = MemoryValidator(args.vault)
    output_file = validator.save_output(generated_by_run=args.generated_by_run)

    print(f"\n🎯 Next steps:")
    print(f"   1. Review: {output_file}")
    print(f"   2. Approved candidates: ready for Obsidian")
    print(f"   3. Rejected candidates: needs revision")
    print(f"   4. When mem0 ready: sync approved_memory")
