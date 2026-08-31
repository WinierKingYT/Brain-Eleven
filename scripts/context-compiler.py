#!/usr/bin/env python3
"""
Brain-Eleven Context Compiler
Smart bootstrap generator: compile top memories + related notes for SessionStart

Pipeline:
  1. Load validated-memory.json
  2. Load Last Session.md + Open Loops
  3. Rank by: type priority + freshness + confidence
  4. Fetch related Hamle notes via wikilinks
  5. Output: context-bootstrap.json (ready for SessionStart hook)
"""

import json
import re
import argparse
import io
from contextlib import redirect_stdout
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Tuple, Set

from memory_scope import filter_memories, infer_memory_scope, resolved_project_identity
from project_registry import registry_path as project_registry_path


def resolve_session_project_id(vault_path: str, project_root: str = None) -> str:
    """Return a registered project ID for SessionStart without creating one."""
    if not project_root:
        return None
    identity = resolved_project_identity(
        project_root,
        project_registry_path(vault_path),
    )
    return identity[0] if identity else None


class ContextCompiler:
    """Compile curated context for session bootstrap"""

    def __init__(self, vault_path: str, project_id: str = None, retrieval_scope: str = "default"):
        self.vault_path = Path(vault_path)
        self.validated_json = self.vault_path / ".claude/validated-memory.json"
        self.last_session_file = self.vault_path / "🔮 Companion/Last Session.md"
        self.open_loops_file = self.vault_path / "🔮 Companion/Açık Döngüler.md"
        self.hamle_dir = self.vault_path / "🗂️ Proje Notları/Kararlar"
        self.project_id = project_id
        self.retrieval_scope = retrieval_scope

        self.memories = []
        self.related_notes = []

    # ========================================================================
    # LOAD DATA
    # ========================================================================

    def _load_validated_memories(self):
        """Load validated memories"""
        if not self.validated_json.exists():
            print("⚠️  validated-memory.json not found")
            return

        with open(self.validated_json, 'r', encoding='utf-8') as f:
            data = json.load(f)

        self.memories = data.get("validated_memory", [])
        print(f"✓ Loaded {len(self.memories)} validated memories")

    def _load_last_session(self) -> str:
        """Load Last Session context"""
        if not self.last_session_file.exists():
            return ""

        with open(self.last_session_file, 'r', encoding='utf-8') as f:
            content = f.read()

        return content

    def _load_open_loops(self) -> str:
        """Load Open Loops"""
        if not self.open_loops_file.exists():
            return ""

        with open(self.open_loops_file, 'r', encoding='utf-8') as f:
            content = f.read()

        return content

    # ========================================================================
    # RANKING
    # ========================================================================

    def _rank_memories(self, limit: int = 5) -> List[Dict]:
        """Rank memories by type priority + freshness + confidence (skip inactive)"""

        type_priority = {
            "decision": 1.0,
            "lesson": 0.8,
            "open_loop": 0.9,
            "observation": 0.6
        }

        scoped_memories = filter_memories(
            self.memories,
            project_id=self.project_id,
            retrieval_scope=self.retrieval_scope,
        )
        ranked = []

        for memory in scoped_memories:
            # Skip inactive memories (prevents memory poisoning)
            status = memory.get("status", "active")
            if status != "active":
                continue

            # Type priority
            priority = type_priority.get(memory["type"], 0.5)

            # Freshness
            try:
                dt = datetime.fromisoformat(memory["timestamp"])
                now = datetime.now()
                days_old = (now - dt).days
                freshness = max(0.3, 1.0 - (days_old * 0.05))
            except:
                freshness = 0.5

            # Combine scores
            confidence = memory["quality_score"]
            score = (priority * 0.4) + (confidence * 0.4) + (freshness * 0.2)

            ranked.append({
                **memory,
                "ranking_score": score
            })

        # Current-project memories form the first scope tier; preserve the
        # existing score ordering within each tier.
        ranked.sort(
            key=lambda m: (
                0 if self.project_id and infer_memory_scope(m)[2] == self.project_id else 1,
                -m["ranking_score"],
            )
        )

        return ranked[:limit]

    # ========================================================================
    # RELATED NOTES
    # ========================================================================

    def _extract_wikilinks(self, text: str) -> Set[str]:
        """Extract wikilinks from text [[hamle-123]] -> hamle-123"""
        pattern = r'\[\[([^\]]+)\]\]'
        matches = re.findall(pattern, text)
        return set(matches)

    def _fetch_related_hamles(self, memories: List[Dict]) -> Dict[str, str]:
        """Fetch related Hamle notes referenced in memories (canonical: related_notes field)"""

        related = {}

        # Canonical source: related_notes field already in memory
        all_links = set()
        for memory in memories:
            # Use the structured related_notes field (primary)
            related_notes = memory.get("related_notes", [])
            all_links.update(related_notes)

            # Fallback: parse wikilinks from content (secondary)
            if not related_notes:
                links = self._extract_wikilinks(memory["content"])
                all_links.update(links)

        # Fetch each Hamle note
        if self.hamle_dir.exists():
            for link in all_links:
                # Try to find the file (handle various formats)
                hamle_file = self.hamle_dir / f"{link}.md"

                if hamle_file.exists():
                    with open(hamle_file, 'r', encoding='utf-8') as f:
                        content = f.read()
                    # Store first 200 chars
                    related[link] = content[:200]

        return related

    # ========================================================================
    # COMPILE CONTEXT
    # ========================================================================

    def compile(self) -> Dict:
        """Generate full bootstrap context"""

        print("\n📋 Brain-Eleven Context Compiler")
        print("=" * 50)

        print("\n1. Loading data...")
        self._load_validated_memories()
        last_session = self._load_last_session()
        open_loops = self._load_open_loops()

        print("\n2. Ranking memories...")
        top_memories = self._rank_memories(limit=5)
        print(f"   → Top 5 memories selected")

        print("\n3. Fetching related Hamle notes...")
        related_hamles = self._fetch_related_hamles(top_memories)
        print(f"   → Found {len(related_hamles)} related notes")

        print("\n4. Compiling context...")

        output = {
            "compiled_at": datetime.now().isoformat(),
            "summary": {
                "top_memories": len(top_memories),
                "retrieval_scope": self.retrieval_scope,
                "project_id": self.project_id,
                "related_hamles": len(related_hamles),
                "has_last_session": bool(last_session),
                "has_open_loops": bool(open_loops)
            },
            "top_memories": top_memories,
            "related_hamles": related_hamles,
            "last_session_summary": last_session[:500] if last_session else "",
            "open_loops_summary": open_loops[:300] if open_loops else "",
            "context_block": self._generate_context_block(
                top_memories, related_hamles, last_session, open_loops
            ),
            "ready_for_session_start": True
        }

        return output

    def _generate_context_block(
        self,
        memories: List[Dict],
        hamles: Dict[str, str],
        last_session: str,
        open_loops: str
    ) -> str:
        """Generate formatted context block for Claude prompt"""

        lines = []

        lines.append("=" * 60)
        lines.append("SESSION BOOTSTRAP CONTEXT (Compiled by Brain-Eleven)")
        lines.append("=" * 60)

        # Last session summary
        if last_session:
            lines.append("\n## LAST SESSION")
            lines.append(last_session[:400])

        # Top memories
        if memories:
            lines.append("\n## TOP MEMORIES")
            lines.append(f"(Most relevant from {len(memories)} validated memories)\n")
            for i, mem in enumerate(memories, 1):
                lines.append(f"{i}. [{mem['type'].upper()}]")
                lines.append(f"   {mem['content'][:150]}...")
                lines.append(f"   Score: {mem['ranking_score']:.2f}")
                lines.append("")

        # Open loops
        if open_loops:
            lines.append("\n## OPEN LOOPS")
            lines.append(open_loops[:300])

        # Related Hamles
        if hamles:
            lines.append("\n## RELATED HAMLE NOTES")
            for name, content in list(hamles.items())[:3]:
                lines.append(f"\n{name}:")
                lines.append(f"  {content[:100]}...")

        lines.append("\n" + "=" * 60)

        return "\n".join(lines)

    def save(self, output_file: str = None) -> str:
        """Compile and save context"""

        if output_file is None:
            output_file = str(self.vault_path / ".claude/context-bootstrap.json")

        output = self.compile()

        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(output, f, indent=2, ensure_ascii=False)

        print(f"\n✅ Context compiled")
        print(f"   → Saved to: {output_file}")
        print(f"\n📝 Context block preview:")
        print(output["context_block"])

        return output_file


# ============================================================================
# CLI
# ============================================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Compile Brain-Eleven session context")
    parser.add_argument("--vault", default=str(Path.home() / "Documents/Brain-Eleven"))
    parser.add_argument("--project-root", default=None)
    parser.add_argument("--project-id", default=None)
    parser.add_argument(
        "--retrieval-scope",
        choices=("default", "global", "project", "all"),
        default="default",
    )
    parser.add_argument("--stdout", action="store_true", help="Print only the context block")
    args = parser.parse_args()

    project_id = args.project_id
    if project_id is None:
        project_id = resolve_session_project_id(args.vault, args.project_root)
    compiler = ContextCompiler(
        args.vault,
        project_id=project_id,
        retrieval_scope=args.retrieval_scope,
    )
    if args.stdout:
        sink = io.StringIO()
        with redirect_stdout(sink):
            output = compiler.compile()
        print(output["context_block"])
    else:
        output_file = compiler.save()
        print(f"\n🎯 Ready for session bootstrap:")
        print(f"   1. SessionStart hook loads: {output_file}")
        print(f"   2. Claude gets full context automatically")
        print(f"   3. No manual re-briefing needed")
