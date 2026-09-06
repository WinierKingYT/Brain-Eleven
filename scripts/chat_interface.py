#!/usr/bin/env python3
"""
Brain-Eleven v3 - Chat Interface (Phase 11C)

Rule-based intent router over the memory system, NOT an LLM chat agent.
PHASE11-KICKSTART.md's original design called GPT-4 for both intent
handling and response generation; no OpenAI key is configured here, so
every handler below calls this repo's own real functions (Phase 7 hybrid
search, Phase 10A summarizer, Phase 10B anomaly detector, Phase 11
knowledge graph) and formats their output with templates. Answers are
grounded in actual stored data - never generated free text. That rules
out classic generative hallucination, but not a wrong answer: bad
retrieval ranking, a mis-resolved entity, a stale graph, or a duplicate
memory in the store can all still produce an answer that's wrong even
though nothing was "made up". "Non-generative, source-grounded" is the
accurate claim here, not "hallucination-free".

If a real LLM becomes available later, the natural upgrade is to keep
IntentClassifier + the handlers' data-fetching as-is and swap only the
final templating step for an LLM call that summarizes the fetched
data - the retrieval/grounding stays deterministic either way.
"""

import re
import json
import uuid
import sys
from pathlib import Path
from datetime import datetime
from enum import Enum
from typing import List, Dict, Optional

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from brain_eleven.support import AnomalyDetector, MemorySummarizer, setup_logging
from brain_eleven.graph import KnowledgeGraph
from brain_eleven.memory.scope import filter_memories
from brain_eleven.search import HybridSearchEngine, MemoryRetriever

logger = setup_logging(__name__)

class Intent(Enum):
    QUERY = "Query for information"
    SUMMARIZE = "Get summary/recap"
    ANOMALY = "Check for issues"
    CREATE = "Add new memory"
    ANALYZE = "Deep analysis"
    REFLECT = "Self-reflection"
    GRAPH = "Graph query"


class IntentClassifier:
    """First-match regex router. Order matters: more specific patterns first."""

    def __init__(self):
        self.patterns = [
            (Intent.ANOMALY, r"(anomaly|anomalies|contradiction|risk|alert|duplicate|stale|broken)"),
            (Intent.SUMMARIZE, r"(summarize|recap|what happened|summary|digest|daily|weekly|monthly)"),
            (Intent.GRAPH, r"(connected|relationship|depends?\b|graph|who uses|what uses|linked to)"),
            (Intent.REFLECT, r"(reflect|lessons learned|what did we learn|thoughts on)"),
            (Intent.CREATE, r"^(remember|note that|remember to)\b"),
            (Intent.ANALYZE, r"(analyze|deep dive|why did|how did|explain)"),
        ]

    def classify(self, user_input: str) -> Intent:
        text = user_input.lower()
        for intent, pattern in self.patterns:
            if re.search(pattern, text):
                return intent
        return Intent.QUERY


class ConversationContext:
    """Rolling window of recent turns for a single conversation."""

    def __init__(self, max_turns: int = 5):
        self.history: List[Dict] = []
        self.max_turns = max_turns
        self.project_id: Optional[str] = None
        self.retrieval_scope: str = "default"

    def add_message(self, role: str, content: str) -> None:
        self.history.append({
            "role": role, "content": content, "timestamp": datetime.now().isoformat(),
        })
        if len(self.history) > self.max_turns * 2:
            self.history = self.history[-self.max_turns * 2:]


class ChatAgent:
    """
    Routes user input to a handler and returns a grounded, templated reply.

    Conversations are held in-process (self.conversations); like the
    original design, this does not persist across restarts - fine for a
    single API process, but a multi-worker deployment would need a shared
    store (Redis, same as the Phase 9 cache) instead.
    """

    def __init__(self, vault_path: str = "."):
        self.vault_path = Path(vault_path)
        self.intent_classifier = IntentClassifier()
        self.conversations: Dict[str, ConversationContext] = {}

        self.memory_retriever = MemoryRetriever(str(vault_path))
        self.hybrid_search = HybridSearchEngine(str(vault_path))
        self.summarizer = MemorySummarizer(str(vault_path))
        self.anomaly_detector = AnomalyDetector(str(vault_path))
        self.graph = KnowledgeGraph(str(vault_path))

    @staticmethod
    def _scope_for(context: Optional[ConversationContext]) -> tuple[Optional[str], str]:
        """Keep direct handler calls backward-compatible and scope-safe."""
        if context is None:
            return None, "default"
        return context.project_id, context.retrieval_scope

    def _load_memories(self, context: Optional[ConversationContext]) -> List[Dict]:
        project_id, retrieval_scope = self._scope_for(context)
        return filter_memories(
            self.summarizer.load_memories(),
            project_id=project_id,
            retrieval_scope=retrieval_scope,
        )

    def chat(
        self,
        user_input: str,
        conversation_id: Optional[str] = None,
        project_id: Optional[str] = None,
        retrieval_scope: str = "default",
    ) -> Dict:
        if not conversation_id:
            conversation_id = str(uuid.uuid4())
        if conversation_id not in self.conversations:
            self.conversations[conversation_id] = ConversationContext()

        context = self.conversations[conversation_id]
        context.project_id = project_id
        context.retrieval_scope = retrieval_scope
        context.add_message("user", user_input)

        intent = self.intent_classifier.classify(user_input)
        handlers = {
            Intent.QUERY: self.handle_query,
            Intent.SUMMARIZE: self.handle_summarize,
            Intent.ANOMALY: self.handle_anomaly,
            Intent.CREATE: self.handle_create,
            Intent.ANALYZE: self.handle_analyze,
            Intent.GRAPH: self.handle_graph_query,
            Intent.REFLECT: self.handle_reflect,
        }
        response_text = handlers[intent](user_input, context)
        context.add_message("assistant", response_text)

        return {
            "response": response_text,
            "conversation_id": conversation_id,
            "intent": intent.name,
            "follow_ups": self._follow_ups(intent),
        }

    # -- handlers -----------------------------------------------------------

    def handle_query(self, query: str, context: Optional[ConversationContext]) -> str:
        memories = self._load_memories(context)
        if not memories:
            return "I don't have any memories stored yet."

        project_id, retrieval_scope = self._scope_for(context)
        results = self.hybrid_search.search(
            query,
            memories,
            top_k=3,
            project_id=project_id,
            retrieval_scope=retrieval_scope,
        )
        if not results:
            return "I don't have information about that in my memory."

        by_id = {m["memory_id"]: m for m in memories}
        lines = ["Based on my memories:", ""]
        for i, result in enumerate(results, 1):
            memory = by_id.get(result.get("memory_id"), {})
            content = memory.get("content", "(content unavailable)")
            score = result.get("combined_score", 0.0)
            lines.append(f"{i}. {content} (relevance: {score:.2f})")
        return "\n".join(lines)

    def handle_summarize(self, query: str, context: Optional[ConversationContext]) -> str:
        days = None
        if "weekly" in query.lower():
            days = 7
        elif "monthly" in query.lower():
            days = 30
        elif "daily" in query.lower() or "today" in query.lower():
            days = 1

        project_id, retrieval_scope = self._scope_for(context)
        digest = self.summarizer.generate_digest(
            days=days,
            top_n_per_type=3,
            project_id=project_id,
            retrieval_scope=retrieval_scope,
        )
        if digest["total_memories_considered"] == 0:
            return "Nothing to summarize for that period."

        lines = [
            f"Summary ({digest['total_memories_considered']} memories, "
            f"{digest['total_after_dedup']} after dedup):", "",
        ]
        for mem_type, items in digest["by_type"].items():
            if not items:
                continue
            lines.append(f"{mem_type.replace('_', ' ').title()}:")
            for item in items:
                lines.append(f"  - {item['content']}")
        return "\n".join(lines)

    def handle_anomaly(self, query: str, context: Optional[ConversationContext]) -> str:
        report = self.anomaly_detector.detect_all()
        if report["total_anomalies"] == 0:
            return "No anomalies detected - the memory store looks clean."

        lines = [f"Found {report['total_anomalies']} anomalies:", ""]
        for sev, count in sorted(report["by_severity"].items(), key=lambda kv: kv[1], reverse=True):
            lines.append(f"  {sev}: {count}")
        lines.append("")
        lines.append("Top issues:")
        for anomaly in report["anomalies"][:5]:
            lines.append(f"  - [{anomaly['type']}] {anomaly['description']}")
        return "\n".join(lines)

    def handle_create(self, query: str, context: Optional[ConversationContext]) -> str:
        # Deliberately does not write to validated-memory.json directly:
        # doing so here would bypass memory-validator.py's quality gate
        # (conflict detection, fingerprint dedup, scoring). Point the
        # caller at the endpoint that actually runs that pipeline.
        return (
            "I won't store that directly from chat - it would skip the "
            "validation pipeline (dedup, conflict checks, quality scoring). "
            "Use POST /memories with the content, type, and confidence instead."
        )

    def handle_analyze(self, query: str, context: Optional[ConversationContext]) -> str:
        project_id, retrieval_scope = self._scope_for(context)
        entities = self._find_subject_entities(
            query, project_id=project_id, retrieval_scope=retrieval_scope
        )
        if not entities:
            return self.handle_query(query, context)

        entity = entities[0]
        subgraph = self.graph.traverse(
            entity["id"],
            max_depth=1,
            project_id=project_id,
            retrieval_scope=retrieval_scope,
        )
        related = [n["name"] for n in subgraph["nodes"] if n["id"] != entity["id"]]

        lines = [f"Analysis of '{entity['name']}' ({entity['type']}):"]
        if related:
            lines.append(f"Connected to: {', '.join(related)}")
        else:
            lines.append("No recorded connections to other entities.")
        return "\n".join(lines)

    def handle_graph_query(self, query: str, context: Optional[ConversationContext]) -> str:
        project_id, retrieval_scope = self._scope_for(context)
        entities = self._find_subject_entities(
            query, project_id=project_id, retrieval_scope=retrieval_scope
        )

        if not entities:
            stats = self.graph.stats()
            return (
                "I couldn't match any known entity in that question. "
                f"The graph currently has {stats['total_entities']} entities "
                f"and {stats['total_relationships']} relationships."
            )

        entity = entities[0]
        relationships = self.graph.get_relationships(
            entity["id"],
            project_id=project_id,
            retrieval_scope=retrieval_scope,
        )
        if not relationships:
            return f"'{entity['name']}' has no recorded relationships."

        lines = [f"Relationships for '{entity['name']}':"]
        for rel in relationships:
            other_id = rel["target"] if rel["source"] == entity["id"] else rel["source"]
            other = self.graph.get_entity(other_id)
            other_name = other["name"] if other else other_id
            lines.append(f"  - {rel['rel_type']}: {other_name}")
        return "\n".join(lines)

    def handle_reflect(self, query: str, context: Optional[ConversationContext]) -> str:
        project_id, retrieval_scope = self._scope_for(context)
        digest = self.summarizer.generate_digest(
            top_n_per_type=3,
            statuses=["active", "resolved"],
            project_id=project_id,
            retrieval_scope=retrieval_scope,
        )
        lessons = digest["by_type"].get("lesson", [])
        decisions = digest["by_type"].get("decision", [])

        if not lessons and not decisions:
            return "No lessons or decisions recorded yet to reflect on."

        lines = ["Reflecting on what's been recorded:"]
        if decisions:
            lines.append("\nKey decisions:")
            lines.extend(f"  - {d['content']}" for d in decisions)
        if lessons:
            lines.append("\nLessons learned:")
            lines.extend(f"  - {l['content']}" for l in lessons)
        return "\n".join(lines)

    # -- helpers --------------------------------------------------------

    QUESTION_STOPWORDS = {
        "what", "who", "which", "how", "is", "are", "does", "do", "the", "a", "an",
        "to", "of", "in", "on", "for", "connected", "connect", "connects", "connection",
        "depends", "depend", "dependent", "relates", "related", "relationship", "linked",
        "link", "uses", "use", "used", "with", "and", "or", "graph",
    }

    # Node types that ARE a memory's own record (entity_extractor.py adds
    # one per memory, named after its type). Ranked below purpose-built
    # entities (TECHNOLOGY, PHASE, ...) below since a query naming a real
    # entity ("Redis") shouldn't resolve to some unrelated memory whose
    # truncated content happens to contain that word.
    MEMORY_NODE_TYPES = {"DECISION", "LESSON", "OBSERVATION", "OPEN_LOOP"}

    def _find_subject_entities(
        self,
        query: str,
        project_id: Optional[str] = None,
        retrieval_scope: str = "default",
    ) -> List[Dict]:
        """
        Match query tokens against actual graph entity names rather than
        guessing from capitalization - entity names here (e.g. "mem0") are
        often lowercase, so a capitalization heuristic alone misses them.
        Tries longer token combinations first so multi-word names win over
        a partial single-word match, then ranks all candidate matches:
        exact name match beats substring, and a purpose-built entity
        (TECHNOLOGY/PHASE) beats a memory-content node with an incidental
        substring hit.
        """
        words = [w for w in re.findall(r"[A-Za-z0-9']+", query)
                 if w.lower() not in self.QUESTION_STOPWORDS]

        candidate_phrases = [
            " ".join(words[i:i + window])
            for window in (2, 1)
            for i in range(len(words) - window + 1)
        ]

        seen_ids = set()
        ranked = []
        for candidate in candidate_phrases:
            for match in self.graph.find_entities(
                name_contains=candidate,
                project_id=project_id,
                retrieval_scope=retrieval_scope,
            ):
                if match["id"] in seen_ids:
                    continue
                seen_ids.add(match["id"])
                is_exact = match["name"].strip().lower() == candidate.strip().lower()
                is_typed_entity = match["type"] not in self.MEMORY_NODE_TYPES
                ranked.append((is_exact, is_typed_entity, match))

        ranked.sort(key=lambda t: (t[0], t[1]), reverse=True)
        return [match for _, _, match in ranked]

    @staticmethod
    def _follow_ups(intent: Intent) -> List[str]:
        options = {
            Intent.QUERY: ["Would you like more details?", "Should I search for something else?"],
            Intent.SUMMARIZE: ["Want a different time period?", "Focus on a specific memory type?"],
            Intent.ANOMALY: ["Should I drill into any of these?", "Want the full report?"],
            Intent.GRAPH: ["Want to see connections one hop further out?"],
            Intent.ANALYZE: ["Should I check the graph for related entities?"],
            Intent.REFLECT: ["Want to see open loops too?"],
        }
        return options.get(intent, [])


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Chat with the Brain-Eleven memory system")
    parser.add_argument("--vault", default=".", help="Path to vault root")
    parser.add_argument("message", help="Message to send")
    args = parser.parse_args()

    agent = ChatAgent(vault_path=args.vault)
    result = agent.chat(args.message)
    print(json.dumps(result, indent=2, ensure_ascii=False))
