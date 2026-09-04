#!/usr/bin/env python3
"""
Brain-Eleven Context Compiler Tests

context-compiler.py had zero test coverage despite being real, currently
used production code (session-start.sh's Step 2 relies on its output,
.claude/context-bootstrap.json) - unlike the one-off migration/demo
scripts excluded via .coveragerc, this one runs on every session.
"""

import sys
import json
import importlib.util
from pathlib import Path
from datetime import datetime, timedelta

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from project_registry import ProjectRegistry  # noqa: E402
from state_store import StateService, StateStore  # noqa: E402

spec = importlib.util.spec_from_file_location(
    "context_compiler", Path(__file__).parent.parent / "scripts" / "context-compiler.py"
)
context_compiler = importlib.util.module_from_spec(spec)
spec.loader.exec_module(context_compiler)
ContextCompiler = context_compiler.ContextCompiler
ContextBootstrapStale = context_compiler.ContextBootstrapStale


def make_memory(**overrides):
    base = {
        "memory_id": "01TESTCTX0000000000000000",
        "type": "decision",
        "content": "Some memory content",
        "confidence": 0.8,
        "quality_score": 0.8,
        "timestamp": datetime.now().isoformat(),
        "status": "active",
        "related_notes": [],
    }
    base.update(overrides)
    return base


@pytest.fixture
def vault(tmp_path):
    (tmp_path / ".claude").mkdir()
    (tmp_path / "🔮 Companion").mkdir()
    (tmp_path / "🗂️ Proje Notları" / "Kararlar").mkdir(parents=True)
    return tmp_path


def write_memories(vault_path, memories):
    with open(vault_path / ".claude" / "validated-memory.json", "w", encoding="utf-8") as f:
        json.dump({"validated_memory": memories}, f)


class TestLoadData:

    def test_load_validated_memories_missing_file(self, vault):
        compiler = ContextCompiler(str(vault))

        compiler._load_validated_memories()

        assert compiler.memories == []

    def test_load_validated_memories_reads_file(self, vault):
        write_memories(vault, [make_memory()])
        compiler = ContextCompiler(str(vault))

        compiler._load_validated_memories()

        assert len(compiler.memories) == 1

    def test_load_last_session_missing_file_returns_empty(self, vault):
        compiler = ContextCompiler(str(vault))

        assert compiler._load_last_session() == ""

    def test_load_last_session_reads_content(self, vault):
        (vault / "🔮 Companion" / "Last Session.md").write_text("Previous session notes", encoding="utf-8")
        compiler = ContextCompiler(str(vault))

        assert compiler._load_last_session() == "Previous session notes"

    def test_load_open_loops_missing_file_returns_empty(self, vault):
        compiler = ContextCompiler(str(vault))

        assert compiler._load_open_loops() == ""

    def test_load_open_loops_reads_content(self, vault):
        (vault / "🔮 Companion" / "Açık Döngüler.md").write_text("- [ ] finish thing", encoding="utf-8")
        compiler = ContextCompiler(str(vault))

        assert "finish thing" in compiler._load_open_loops()


class TestRankMemories:

    def test_skips_inactive_memories(self, vault):
        compiler = ContextCompiler(str(vault))
        compiler.memories = [
            make_memory(memory_id="a", status="active"),
            make_memory(memory_id="b", status="superseded"),
            make_memory(memory_id="c", status="resolved"),
        ]

        ranked = compiler._rank_memories(limit=5)

        assert {m["memory_id"] for m in ranked} == {"a"}

    def test_respects_limit(self, vault):
        compiler = ContextCompiler(str(vault))
        compiler.memories = [make_memory(memory_id=f"m{i}") for i in range(10)]

        ranked = compiler._rank_memories(limit=3)

        assert len(ranked) == 3

    def test_decision_ranks_above_observation_at_equal_confidence(self, vault):
        compiler = ContextCompiler(str(vault))
        compiler.memories = [
            make_memory(memory_id="obs", type="observation", quality_score=0.8),
            make_memory(memory_id="dec", type="decision", quality_score=0.8),
        ]

        ranked = compiler._rank_memories(limit=5)

        assert ranked[0]["memory_id"] == "dec"

    def test_fresher_memory_scores_higher_at_equal_priority_and_confidence(self, vault):
        compiler = ContextCompiler(str(vault))
        old_ts = (datetime.now() - timedelta(days=60)).isoformat()
        new_ts = datetime.now().isoformat()
        compiler.memories = [
            make_memory(memory_id="old", type="decision", quality_score=0.8, timestamp=old_ts),
            make_memory(memory_id="new", type="decision", quality_score=0.8, timestamp=new_ts),
        ]

        ranked = compiler._rank_memories(limit=5)

        assert ranked[0]["memory_id"] == "new"

    def test_malformed_timestamp_falls_back_to_default_freshness(self, vault):
        compiler = ContextCompiler(str(vault))
        compiler.memories = [make_memory(timestamp="not-a-real-timestamp")]

        ranked = compiler._rank_memories(limit=5)

        assert len(ranked) == 1  # doesn't raise, just scores with the fallback

    def test_unknown_type_uses_default_priority(self, vault):
        compiler = ContextCompiler(str(vault))
        compiler.memories = [make_memory(type="some_new_type")]

        ranked = compiler._rank_memories(limit=5)

        assert len(ranked) == 1

    def test_ranked_memories_include_ranking_score_field(self, vault):
        compiler = ContextCompiler(str(vault))
        compiler.memories = [make_memory()]

        ranked = compiler._rank_memories(limit=5)

        assert "ranking_score" in ranked[0]


class TestWikilinksAndHamles:

    def test_extract_wikilinks_finds_all_links(self, vault):
        compiler = ContextCompiler(str(vault))

        links = compiler._extract_wikilinks("See [[hamle-1]] and also [[hamle-2]] for details")

        assert links == {"hamle-1", "hamle-2"}

    def test_extract_wikilinks_no_links_returns_empty_set(self, vault):
        compiler = ContextCompiler(str(vault))

        assert compiler._extract_wikilinks("no links here") == set()

    def test_fetch_related_hamles_uses_related_notes_field(self, vault):
        (vault / "🗂️ Proje Notları" / "Kararlar" / "hamle-1.md").write_text(
            "Hamle content here", encoding="utf-8"
        )
        compiler = ContextCompiler(str(vault))
        memories = [make_memory(related_notes=["hamle-1"])]

        related = compiler._fetch_related_hamles(memories)

        assert "hamle-1" in related
        assert "Hamle content here" in related["hamle-1"]

    def test_fetch_related_hamles_falls_back_to_wikilinks_when_no_related_notes(self, vault):
        (vault / "🗂️ Proje Notları" / "Kararlar" / "hamle-2.md").write_text(
            "Fallback hamle", encoding="utf-8"
        )
        compiler = ContextCompiler(str(vault))
        memories = [make_memory(related_notes=[], content="Decided based on [[hamle-2]]")]

        related = compiler._fetch_related_hamles(memories)

        assert "hamle-2" in related

    def test_fetch_related_hamles_missing_hamle_dir_returns_empty(self, tmp_path):
        (tmp_path / ".claude").mkdir()
        (tmp_path / "🔮 Companion").mkdir()
        # deliberately do NOT create the Kararlar dir
        compiler = ContextCompiler(str(tmp_path))

        related = compiler._fetch_related_hamles([make_memory(related_notes=["hamle-1"])])

        assert related == {}

    def test_fetch_related_hamles_missing_file_is_skipped(self, vault):
        compiler = ContextCompiler(str(vault))

        related = compiler._fetch_related_hamles([make_memory(related_notes=["does-not-exist"])])

        assert related == {}


class TestCompileAndSave:

    def test_compile_returns_expected_structure(self, vault):
        write_memories(vault, [make_memory()])
        compiler = ContextCompiler(str(vault))

        output = compiler.compile()

        assert output["ready_for_session_start"] is True
        assert output["schema_version"] == 3
        assert output["projection"] == "context_bootstrap"
        assert output["source_memory_revision"] == 0
        assert "context_block" in output
        assert output["summary"]["top_memories"] == 1

    def test_compile_carries_session_run_lineage_when_provided(self, vault):
        compiler = ContextCompiler(str(vault), generated_by_run="run_test")

        output = compiler.compile()

        assert output["generated_by_run"] == "run_test"

    def test_compile_with_no_memories_still_succeeds(self, vault):
        compiler = ContextCompiler(str(vault))

        output = compiler.compile()

        assert output["summary"]["top_memories"] == 0
        assert output["summary"]["has_last_session"] is False

    def test_compile_reports_last_session_and_open_loops_presence(self, vault):
        (vault / "🔮 Companion" / "Last Session.md").write_text("notes", encoding="utf-8")
        (vault / "🔮 Companion" / "Açık Döngüler.md").write_text("- [ ] task", encoding="utf-8")
        compiler = ContextCompiler(str(vault))

        output = compiler.compile()

        assert output["summary"]["has_last_session"] is True
        assert output["summary"]["has_open_loops"] is True

    def test_context_block_includes_top_memories_section(self, vault):
        write_memories(vault, [make_memory(content="A decision worth remembering")])
        compiler = ContextCompiler(str(vault))

        output = compiler.compile()

        assert "TOP MEMORIES" in output["context_block"]
        assert "A decision worth remembering" in output["context_block"]

    def test_context_block_omits_sections_with_no_data(self, vault):
        compiler = ContextCompiler(str(vault))

        output = compiler.compile()

        assert "LAST SESSION" not in output["context_block"]
        assert "OPEN LOOPS" not in output["context_block"]

    def test_save_writes_json_file(self, vault):
        write_memories(vault, [make_memory()])
        compiler = ContextCompiler(str(vault))

        output_path = compiler.save()

        assert Path(output_path).exists()
        with open(output_path, encoding="utf-8") as f:
            data = json.load(f)
        assert data["ready_for_session_start"] is True

    def test_saved_bootstrap_is_readable_only_when_current(self, vault):
        write_memories(vault, [make_memory()])
        compiler = ContextCompiler(str(vault), project_id="project-a")
        compiler.save()

        status = ContextCompiler(str(vault), project_id="project-a").bootstrap_status()

        assert status["status"] == "fresh"
        assert "SESSION BOOTSTRAP CONTEXT" in status["context_block"]

    def test_saved_bootstrap_is_rejected_after_canonical_revision_changes(self, vault):
        write_memories(vault, [make_memory()])
        compiler = ContextCompiler(str(vault), project_id="project-a")
        compiler.save()
        context_compiler.MemoryStore(vault).append(make_memory(memory_id="new-memory"))

        status = ContextCompiler(str(vault), project_id="project-a").bootstrap_status()

        assert status["status"] == "stale"
        assert status["context_block"] is None

    def test_saved_bootstrap_is_rejected_for_a_different_project_scope(self, vault):
        write_memories(vault, [make_memory()])
        ContextCompiler(str(vault), project_id="project-a").save()

        status = ContextCompiler(str(vault), project_id="project-b").bootstrap_status()

        assert status["status"] == "scope_mismatch"
        assert status["context_block"] is None

    def test_corrupt_bootstrap_is_never_exposed_to_session_start(self, vault):
        bootstrap = vault / ".claude" / "context-bootstrap.json"
        bootstrap.write_text("{not valid json", encoding="utf-8")

        status = ContextCompiler(str(vault)).bootstrap_status()

        assert status["status"] == "corrupt"
        assert status["context_block"] is None

    def test_save_does_not_overwrite_prior_bootstrap_after_revision_race(self, vault):
        write_memories(vault, [make_memory()])
        bootstrap = vault / ".claude" / "context-bootstrap.json"
        bootstrap.write_text('{"previous": true}', encoding="utf-8")
        compiler = ContextCompiler(str(vault))

        def mutate_store_during_compile(_memories):
            context_compiler.MemoryStore(vault).append(make_memory(memory_id="concurrent"))
            return {}

        compiler._fetch_related_hamles = mutate_store_during_compile

        with pytest.raises(ContextBootstrapStale):
            compiler.save()

        assert json.loads(bootstrap.read_text(encoding="utf-8")) == {"previous": True}

    def test_save_uses_default_output_path(self, vault):
        compiler = ContextCompiler(str(vault))

        output_path = compiler.save()

        assert output_path == str(vault / ".claude" / "context-bootstrap.json")

    def test_bootstrap_includes_current_state_and_rejects_a_changed_state_revision(self, vault):
        ProjectRegistry(vault).register(vault / "project-a", project_id="project-a")
        service = StateService(vault)
        service.init_project("project-a", source={"type": "user", "reference": "test"})
        service.set_current_milestone(
            "project-a",
            phase_id="phase-16",
            title="Task + State Model",
            expected_revision=1,
            source={"type": "user", "reference": "test"},
            record_id="mil_context_state",
        )
        compiler = ContextCompiler(str(vault), project_id="project-a")
        compiler.save()

        output = json.loads((vault / ".claude" / "context-bootstrap.json").read_text(encoding="utf-8"))
        assert output["source_state_revision"] == 2
        assert output["source_state_status"] == "AVAILABLE"
        assert "CURRENT PROJECT STATE" in output["context_block"]
        assert "Phase: phase-16" in output["context_block"]

        service.set_current_objective(
            "project-a",
            text="A state update invalidates the derived bootstrap",
            expected_revision=2,
            source={"type": "user", "reference": "test"},
            record_id="obj_context_state",
        )
        status = ContextCompiler(str(vault), project_id="project-a").bootstrap_status()
        assert status["status"] == "stale"
        assert status["context_block"] is None

    def test_corrupt_current_state_is_never_injected_as_empty_bootstrap(self, vault):
        ProjectRegistry(vault).register(vault / "project-a", project_id="project-a")
        state_path = StateStore(vault).path
        state_path.write_text("{not valid json", encoding="utf-8")

        with pytest.raises(context_compiler.ContextBootstrapError, match="unavailable"):
            ContextCompiler(str(vault), project_id="project-a").compile()
