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
import os
import tempfile
from contextlib import redirect_stdout
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Tuple, Set, Optional

from memory_scope import filter_memories, infer_memory_scope, resolve_retrieval_project
from memory_store import MemoryStore, MemoryStoreError
from project_registry import registry_path as project_registry_path


CONTEXT_BOOTSTRAP_SCHEMA_VERSION = 2


class ContextBootstrapError(RuntimeError):
    """Base class for derived context-bootstrap failures."""


class ContextBootstrapStale(ContextBootstrapError):
    """Raised when a compiled bootstrap no longer matches canonical memory."""


def resolve_session_project_id(vault_path: str, project_root: str = None) -> str:
    """Return a registered project ID for SessionStart without creating one."""
    if not project_root:
        return None
    identity = resolve_retrieval_project(
        project_root,
        project_registry_path(vault_path),
    )
    return identity[0] if identity else None


class ContextCompiler:
    """Compile curated context for session bootstrap"""

    def __init__(self, vault_path: str, project_id: str = None, retrieval_scope: str = "default"):
        self.vault_path = Path(vault_path)
        self.validated_json = self.vault_path / ".claude/validated-memory.json"
        self.memory_store = MemoryStore(self.vault_path)
        self.last_session_file = self.vault_path / "🔮 Companion/Last Session.md"
        self.open_loops_file = self.vault_path / "🔮 Companion/Açık Döngüler.md"
        self.hamle_dir = self.vault_path / "🗂️ Proje Notları/Kararlar"
        self.project_id = project_id
        self.retrieval_scope = retrieval_scope

        self.memories = []
        self.related_notes = []
        self.source_memory_revision: Optional[int] = None

    # ========================================================================
    # LOAD DATA
    # ========================================================================

    def _load_validated_memories(self):
        """Load validated memories"""
        if not self.validated_json.exists():
            self.memories = []
            self.source_memory_revision = self.memory_store.revision()
            print("⚠️  validated-memory.json not found")
            return

        data = self.memory_store.load()
        self.source_memory_revision = int(data["revision"])
        self.memories = data.get("validated_memory", [])
        print(f"✓ Loaded {len(self.memories)} validated memories")

    # ========================================================================
    # DERIVED-PROJECTION SAFETY
    # ========================================================================

    def _bootstrap_path(self, output_file: str = None) -> Path:
        return Path(output_file) if output_file else self.vault_path / ".claude/context-bootstrap.json"

    def _ensure_output_is_current(self, output: Dict) -> None:
        """Refuse to publish context compiled from an obsolete store snapshot."""
        source_revision = output.get("source_memory_revision")
        if not isinstance(source_revision, int) or source_revision < 0:
            raise ContextBootstrapError("Bootstrap source revision must be a non-negative integer")

        current_revision = self.memory_store.revision()
        if source_revision != current_revision:
            raise ContextBootstrapStale(
                "Canonical memory store changed during context compilation: "
                f"started at revision {source_revision}, now {current_revision}"
            )

    def bootstrap_status(self, output_file: str = None) -> Dict:
        """Return whether a saved bootstrap is safe for this session to inject.

        A bootstrap is a derived projection. It is readable only when its
        schema, canonical-memory revision, and project retrieval scope all
        exactly match the current session. Callers receive no context block for
        missing, corrupt, stale, or scope-mismatched files.
        """
        bootstrap_path = self._bootstrap_path(output_file)
        status = {
            "status": "missing",
            "path": str(bootstrap_path),
            "source_memory_revision": None,
            "context_block": None,
            "error": None,
        }
        if not bootstrap_path.exists():
            return status

        try:
            data = json.loads(bootstrap_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            status.update(status="corrupt", error=str(exc))
            return status

        if not isinstance(data, dict):
            status.update(status="corrupt", error="Bootstrap must be a JSON object")
            return status
        if data.get("schema_version") != CONTEXT_BOOTSTRAP_SCHEMA_VERSION:
            status.update(status="corrupt", error="Unsupported context bootstrap schema version")
            return status
        if data.get("projection") != "context_bootstrap":
            status.update(status="corrupt", error="Unexpected context bootstrap projection name")
            return status

        source_revision = data.get("source_memory_revision")
        status["source_memory_revision"] = source_revision
        if not isinstance(source_revision, int) or source_revision < 0:
            status.update(status="corrupt", error="Bootstrap source revision must be a non-negative integer")
            return status
        if data.get("ready_for_session_start") is not True:
            status.update(status="corrupt", error="Bootstrap is not marked ready for SessionStart")
            return status

        summary = data.get("summary")
        block = data.get("context_block")
        if not isinstance(summary, dict) or not isinstance(block, str):
            status.update(status="corrupt", error="Bootstrap summary or context block is invalid")
            return status
        if (
            summary.get("project_id") != self.project_id
            or summary.get("retrieval_scope") != self.retrieval_scope
        ):
            status.update(status="scope_mismatch")
            return status

        try:
            current_revision = self.memory_store.revision()
        except MemoryStoreError as exc:
            status.update(status="source_unavailable", error=str(exc))
            return status
        if source_revision != current_revision:
            status.update(status="stale")
            return status

        status.update(status="fresh", context_block=block)
        return status

    @staticmethod
    def _atomic_write_json(path: Path, data: Dict) -> None:
        """Persist a derived bootstrap atomically, never exposing partial JSON."""
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=".context-bootstrap-", suffix=".json", dir=path.parent
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(data, handle, indent=2, ensure_ascii=False)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            Path(temporary_name).replace(path)
        except OSError as exc:
            raise ContextBootstrapError(f"Cannot persist context bootstrap: {path}") from exc
        finally:
            temporary = Path(temporary_name)
            if temporary.exists():
                temporary.unlink()

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
            "schema_version": CONTEXT_BOOTSTRAP_SCHEMA_VERSION,
            "projection": "context_bootstrap",
            "source_memory_revision": int(self.source_memory_revision),
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
        """Compile and atomically save a bootstrap only if its snapshot is current."""

        output = self.compile()
        self._ensure_output_is_current(output)
        output_path = self._bootstrap_path(output_file)
        self._atomic_write_json(output_path, output)

        print(f"\n✅ Context compiled")
        print(f"   → Saved to: {output_path}")
        print(f"\n📝 Context block preview:")
        print(output["context_block"])

        return str(output_path)


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
    parser.add_argument(
        "--load-bootstrap",
        action="store_true",
        help="Print the saved bootstrap only when its revision and scope are current",
    )
    args = parser.parse_args()

    project_id = args.project_id
    if project_id is None:
        project_id = resolve_session_project_id(args.vault, args.project_root)
    compiler = ContextCompiler(
        args.vault,
        project_id=project_id,
        retrieval_scope=args.retrieval_scope,
    )
    if args.load_bootstrap:
        status = compiler.bootstrap_status()
        if status["status"] != "fresh":
            raise SystemExit(1)
        print(status["context_block"])
    elif args.stdout:
        sink = io.StringIO()
        with redirect_stdout(sink):
            output = compiler.compile()
            compiler._ensure_output_is_current(output)
        print(output["context_block"])
    else:
        output_file = compiler.save()
        print(f"\n🎯 Ready for session bootstrap:")
        print(f"   1. SessionStart hook loads: {output_file}")
        print(f"   2. Claude gets full context automatically")
        print(f"   3. No manual re-briefing needed")
