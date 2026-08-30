#!/usr/bin/env python3
"""
Phase 11: Knowledge Graph, Entity Extraction & Chat Interface Tests

Neither module needs a real Neo4j instance or an LLM (see module
docstrings in knowledge_graph.py / entity_extractor.py / chat_interface.py
for why) - tests run entirely offline against synthetic fixtures.
"""

import sys
import json
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from knowledge_graph import KnowledgeGraph  # noqa: E402
from entity_extractor import EntityExtractor, TECH_LEXICON  # noqa: E402
from chat_interface import IntentClassifier, Intent, ChatAgent  # noqa: E402


def make_memory(**overrides):
    base = {
        "memory_id": "01TEST0000000000000000000",
        "source_id": "daily:2026-08-28:observation:0:0",
        "type": "observation",
        "content": "Some memory content",
        "confidence": 0.8,
        "timestamp": "2026-08-28T12:00:00",
        "quality_score": 0.8,
        "status": "active",
        "is_approved": True,
        "superseded_by": "",
    }
    base.update(overrides)
    return base


def write_memories(vault_path, memories):
    claude_dir = vault_path / ".claude"
    claude_dir.mkdir(exist_ok=True)
    with open(claude_dir / "validated-memory.json", "w", encoding="utf-8") as f:
        json.dump({"validated_memory": memories}, f)


@pytest.fixture
def vault(tmp_path):
    (tmp_path / ".claude").mkdir()
    return tmp_path


# ---------------------------------------------------------------------------
# KnowledgeGraph (Phase 11A)
# ---------------------------------------------------------------------------

class TestKnowledgeGraph:

    def test_add_and_get_entity(self, vault):
        kg = KnowledgeGraph(str(vault))
        kg.add_entity("e1", "TECHNOLOGY", "Redis")

        entity = kg.get_entity("e1")

        assert entity["name"] == "Redis"
        assert entity["type"] == "TECHNOLOGY"

    def test_get_missing_entity_returns_none(self, vault):
        kg = KnowledgeGraph(str(vault))

        assert kg.get_entity("nope") is None

    def test_re_adding_entity_merges_properties(self, vault):
        kg = KnowledgeGraph(str(vault))
        kg.add_entity("e1", "TECHNOLOGY", "Redis", version="6")
        kg.add_entity("e1", "TECHNOLOGY", "Redis", version="7")

        entity = kg.get_entity("e1")

        assert entity["version"] == "7"
        assert kg.graph.number_of_nodes() == 1  # not duplicated

    def test_add_relationship_requires_both_entities_exist(self, vault):
        kg = KnowledgeGraph(str(vault))
        kg.add_entity("e1", "TECHNOLOGY", "Redis")

        with pytest.raises(ValueError):
            kg.add_relationship("e1", "USES", "missing")

    def test_add_relationship_creates_edge(self, vault):
        kg = KnowledgeGraph(str(vault))
        kg.add_entity("a", "DECISION", "Use Redis")
        kg.add_entity("b", "TECHNOLOGY", "Redis")
        kg.add_relationship("a", "USES", "b", source_memory="a")

        rels = kg.get_relationships("a", direction="out")

        assert len(rels) == 1
        assert rels[0]["rel_type"] == "USES"

    def test_duplicate_relationship_from_same_source_memory_not_added_twice(self, vault):
        kg = KnowledgeGraph(str(vault))
        kg.add_entity("a", "DECISION", "Use Redis")
        kg.add_entity("b", "TECHNOLOGY", "Redis")
        kg.add_relationship("a", "USES", "b", source_memory="a")
        kg.add_relationship("a", "USES", "b", source_memory="a")

        rels = kg.get_relationships("a", direction="out")

        assert len(rels) == 1

    def test_find_entities_by_type(self, vault):
        kg = KnowledgeGraph(str(vault))
        kg.add_entity("a", "TECHNOLOGY", "Redis")
        kg.add_entity("b", "DECISION", "Use Redis")

        found = kg.find_entities(entity_type="TECHNOLOGY")

        assert len(found) == 1
        assert found[0]["id"] == "a"

    def test_find_entities_by_name_contains_is_case_insensitive(self, vault):
        kg = KnowledgeGraph(str(vault))
        kg.add_entity("a", "TECHNOLOGY", "Redis")

        found = kg.find_entities(name_contains="red")

        assert len(found) == 1

    def test_get_relationships_direction_filtering(self, vault):
        kg = KnowledgeGraph(str(vault))
        kg.add_entity("a", "DECISION", "A")
        kg.add_entity("b", "TECHNOLOGY", "B")
        kg.add_relationship("a", "USES", "b", source_memory="a")

        out_only = kg.get_relationships("b", direction="out")
        in_only = kg.get_relationships("b", direction="in")

        assert out_only == []
        assert len(in_only) == 1

    def test_traverse_respects_max_depth(self, vault):
        kg = KnowledgeGraph(str(vault))
        for node_id in ("a", "b", "c"):
            kg.add_entity(node_id, "TECHNOLOGY", node_id)
        kg.add_relationship("a", "USES", "b", source_memory="a")
        kg.add_relationship("b", "USES", "c", source_memory="b")

        depth1 = kg.traverse("a", max_depth=1)
        depth2 = kg.traverse("a", max_depth=2)

        depth1_ids = {n["id"] for n in depth1["nodes"]}
        depth2_ids = {n["id"] for n in depth2["nodes"]}
        assert depth1_ids == {"a", "b"}
        assert depth2_ids == {"a", "b", "c"}

    def test_find_path_returns_shortest_path(self, vault):
        kg = KnowledgeGraph(str(vault))
        for node_id in ("a", "b", "c"):
            kg.add_entity(node_id, "TECHNOLOGY", node_id)
        kg.add_relationship("a", "USES", "b", source_memory="a")
        kg.add_relationship("b", "USES", "c", source_memory="b")

        path = kg.find_path("a", "c")

        assert path == ["a", "b", "c"]

    def test_find_path_returns_none_when_unreachable(self, vault):
        kg = KnowledgeGraph(str(vault))
        kg.add_entity("a", "TECHNOLOGY", "A")
        kg.add_entity("b", "TECHNOLOGY", "B")

        assert kg.find_path("a", "b") is None

    def test_stats_counts_by_type(self, vault):
        kg = KnowledgeGraph(str(vault))
        kg.add_entity("a", "TECHNOLOGY", "A")
        kg.add_entity("b", "TECHNOLOGY", "B")
        kg.add_entity("c", "DECISION", "C")
        kg.add_relationship("c", "USES", "a", source_memory="c")

        stats = kg.stats()

        assert stats["total_entities"] == 3
        assert stats["entities_by_type"]["TECHNOLOGY"] == 2
        assert stats["relationships_by_type"]["USES"] == 1

    def test_save_and_reload_roundtrip(self, vault):
        kg = KnowledgeGraph(str(vault))
        kg.add_entity("a", "TECHNOLOGY", "Redis")
        kg.add_entity("b", "DECISION", "Use Redis")
        kg.add_relationship("b", "USES", "a", source_memory="b")
        kg.save()

        reloaded = KnowledgeGraph(str(vault))

        assert reloaded.stats() == kg.stats()
        assert reloaded.get_entity("a")["name"] == "Redis"

    def test_missing_graph_file_starts_empty(self, vault):
        kg = KnowledgeGraph(str(vault))

        assert kg.stats()["total_entities"] == 0


# ---------------------------------------------------------------------------
# EntityExtractor (Phase 11B)
# ---------------------------------------------------------------------------

class TestEntityExtractor:

    def test_find_technologies_matches_lexicon(self, vault):
        extractor = EntityExtractor(str(vault))

        found = extractor.find_technologies("We deployed with Docker and Redis today")

        assert "Docker" in found
        assert "Redis" in found

    def test_find_technologies_is_case_insensitive(self, vault):
        extractor = EntityExtractor(str(vault))

        found = extractor.find_technologies("running on DOCKER")

        assert "Docker" in found

    def test_find_technologies_no_match_returns_empty(self, vault):
        extractor = EntityExtractor(str(vault))

        found = extractor.find_technologies("just a regular sentence")

        assert found == []

    def test_find_phase_references_extracts_numbers(self, vault):
        extractor = EntityExtractor(str(vault))

        found = extractor.find_phase_references("Completed Phase 7 and started Phase 8")

        assert found == [7, 8]

    def test_extract_from_memory_creates_memory_node(self, vault):
        extractor = EntityExtractor(str(vault))
        kg = KnowledgeGraph(str(vault))
        memory = make_memory(memory_id="m1", type="decision", content="Chose Redis for caching")

        entities_added, relationships_added = extractor.extract_from_memory(memory, kg)

        assert kg.get_entity("m1")["type"] == "DECISION"
        assert entities_added >= 1
        assert relationships_added >= 1  # Redis mention -> relationship

    def test_decision_type_uses_uses_relationship(self, vault):
        extractor = EntityExtractor(str(vault))
        kg = KnowledgeGraph(str(vault))
        memory = make_memory(memory_id="m1", type="decision", content="Chose Redis for caching")

        extractor.extract_from_memory(memory, kg)

        rels = kg.get_relationships("m1", direction="out", rel_type="USES")
        assert len(rels) == 1

    def test_non_decision_type_uses_mentions_relationship(self, vault):
        extractor = EntityExtractor(str(vault))
        kg = KnowledgeGraph(str(vault))
        memory = make_memory(memory_id="m1", type="observation", content="Noticed Redis was slow")

        extractor.extract_from_memory(memory, kg)

        rels = kg.get_relationships("m1", direction="out", rel_type="MENTIONS")
        assert len(rels) == 1

    def test_phase_reference_creates_relates_to_relationship(self, vault):
        extractor = EntityExtractor(str(vault))
        kg = KnowledgeGraph(str(vault))
        memory = make_memory(memory_id="m1", content="Working on Phase 9 now")

        extractor.extract_from_memory(memory, kg)

        rels = kg.get_relationships("m1", direction="out", rel_type="RELATES_TO")
        assert len(rels) == 1
        assert kg.get_entity(rels[0]["target"])["name"] == "Phase 9"

    def test_build_graph_processes_all_memories(self, vault):
        write_memories(vault, [
            make_memory(memory_id="m1", content="Chose Redis for caching", type="decision"),
            make_memory(memory_id="m2", content="Nothing technical here"),
        ])
        extractor = EntityExtractor(str(vault))

        graph = extractor.build_graph(save=False)

        assert graph.get_entity("m1") is not None
        assert graph.get_entity("m2") is not None

    def test_build_graph_with_no_memories_is_empty(self, vault):
        extractor = EntityExtractor(str(vault))

        graph = extractor.build_graph(save=False)

        assert graph.stats()["total_entities"] == 0


# ---------------------------------------------------------------------------
# IntentClassifier (Phase 11C)
# ---------------------------------------------------------------------------

class TestIntentClassifier:

    @pytest.mark.parametrize("text,expected", [
        ("Can you summarize what happened today?", Intent.SUMMARIZE),
        ("Give me a weekly digest", Intent.SUMMARIZE),
        ("Are there any anomalies or duplicates?", Intent.ANOMALY),
        ("What is Redis connected to?", Intent.GRAPH),
        ("What does the API depend on?", Intent.GRAPH),
        ("Reflect on what we learned", Intent.REFLECT),
        ("remember to update the docs", Intent.CREATE),
        ("Why did we choose FastAPI?", Intent.ANALYZE),
        ("What time did we deploy?", Intent.QUERY),
    ])
    def test_classify_routes_to_expected_intent(self, text, expected):
        classifier = IntentClassifier()

        result = classifier.classify(text)

        assert result == expected

    def test_unmatched_text_defaults_to_query(self):
        classifier = IntentClassifier()

        result = classifier.classify("asdkfjaslkdfj")

        assert result == Intent.QUERY


# ---------------------------------------------------------------------------
# ChatAgent (Phase 11C) - integration across search/summarize/anomaly/graph
# ---------------------------------------------------------------------------

class TestChatAgent:

    def test_chat_returns_conversation_id_and_intent(self, vault):
        write_memories(vault, [make_memory(content="Deployed the search API to production")])
        agent = ChatAgent(str(vault))

        result = agent.chat("Can you summarize recent work?")

        assert result["conversation_id"]
        assert result["intent"] == "SUMMARIZE"
        assert isinstance(result["response"], str)

    def test_reusing_conversation_id_keeps_history(self, vault):
        write_memories(vault, [make_memory(content="Deployed the search API to production")])
        agent = ChatAgent(str(vault))

        first = agent.chat("Summarize things")
        conv_id = first["conversation_id"]
        agent.chat("Anything else?", conversation_id=conv_id)

        assert len(agent.conversations[conv_id].history) == 4  # 2 user + 2 assistant

    def test_handle_query_with_no_memories(self, vault):
        agent = ChatAgent(str(vault))

        response = agent.handle_query("anything?", None)

        assert "don't have any memories" in response

    def test_handle_anomaly_reports_clean_store(self, vault):
        write_memories(vault, [make_memory(content="A perfectly normal unique entry here")])
        agent = ChatAgent(str(vault))

        response = agent.handle_anomaly("check for issues", None)

        assert "clean" in response.lower() or "No anomalies" in response

    def test_handle_anomaly_reports_found_issues(self, vault):
        write_memories(vault, [
            make_memory(memory_id="a", content="Deployed the search API to production"),
            make_memory(memory_id="b", content="Deployed the search API to production"),
        ])
        agent = ChatAgent(str(vault))

        response = agent.handle_anomaly("check for issues", None)

        assert "Found" in response

    def test_handle_create_does_not_persist(self, vault):
        write_memories(vault, [make_memory()])
        agent = ChatAgent(str(vault))

        response = agent.handle_create("remember to fix the bug", None)

        assert "won't store" in response.lower() or "POST /memories" in response
        # confirm nothing was written
        with open(vault / ".claude" / "validated-memory.json", encoding="utf-8") as f:
            data = json.load(f)
        assert len(data["validated_memory"]) == 1

    def test_handle_graph_query_finds_entity_by_lowercase_name(self, vault):
        write_memories(vault, [make_memory(content="Nothing relevant")])
        agent = ChatAgent(str(vault))
        agent.graph.add_entity("tech_mem0", "TECHNOLOGY", "mem0")
        agent.graph.add_entity("dec_1", "DECISION", "Use mem0 for storage")
        agent.graph.add_relationship("dec_1", "USES", "tech_mem0", source_memory="dec_1")

        response = agent.handle_graph_query("What is mem0 connected to?", None)

        assert "mem0" in response
        assert "no known entity" not in response.lower()

    def test_handle_graph_query_reports_when_entity_not_found(self, vault):
        write_memories(vault, [make_memory()])
        agent = ChatAgent(str(vault))

        response = agent.handle_graph_query("What is Kubernetes connected to?", None)

        assert "couldn't match" in response.lower()

    def test_handle_reflect_with_no_lessons_or_decisions(self, vault):
        write_memories(vault, [make_memory(type="observation")])
        agent = ChatAgent(str(vault))

        response = agent.handle_reflect("reflect on this", None)

        assert "no lessons" in response.lower() or "No lessons" in response

    def test_handle_reflect_surfaces_lessons_and_decisions(self, vault):
        write_memories(vault, [
            make_memory(memory_id="a", type="lesson", content="Always write tests first"),
            make_memory(memory_id="b", type="decision", content="Chose FastAPI for the API layer"),
        ])
        agent = ChatAgent(str(vault))

        response = agent.handle_reflect("reflect on this", None)

        assert "Always write tests first" in response
        assert "Chose FastAPI" in response
