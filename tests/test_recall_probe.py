"""Automated five-question recall probe over a real runtime vault."""

from brain_eleven.runtime import recall_probe
from brain_eleven.runtime.recall_probe import covers, probe
from tests.test_memclaim01_claim_key import NEW_TIME, _accept, _review_item, _runtime


def test_covers_needs_every_group_and_folds_turkish_case():
    groups = [["holdout", "corpus-v2"], ["kırmızı", "red"]]
    assert covers("Holdout kapısı KIRMIZI bırakıldı", groups)
    assert not covers("holdout gate stays", groups)


def test_probe_separates_in_context_from_in_memory_and_missing(tmp_path, monkeypatch):
    vault, _ = _runtime(tmp_path, shadow_accept=True)
    _accept(vault, _review_item(tmp_path, vault, "q1",
                                "We decided that the holdout corpus-v2 gate stays red by decision.", NEW_TIME))

    result = probe(vault)
    by_id = {r["id"]: r for r in result["results"]}
    assert by_id[1]["status"] == "IN_CONTEXT"
    assert by_id[5]["status"] == "NOT_IN_MEMORY"
    assert (result["score"], result["of"]) == (1, 5)

    # Same memory, but the bootstrap did not deliver it: a selection problem.
    import brain_eleven.runtime.context as context
    monkeypatch.setattr(context, "compile_bootstrap", lambda *a, **k: {"status": "SUCCESS", "context": "", "selected_ids": []})
    by_id = {r["id"]: r for r in probe(vault)["results"]}
    assert by_id[1]["status"] == "IN_MEMORY_NOT_DELIVERED" and by_id[1]["memory_ids"]


def test_questions_file_matches_the_owner_test_log():
    questions = recall_probe.load_questions()
    assert [q["id"] for q in questions] == [1, 2, 3, 4, 5]
    assert all(q["groups"] and all(q["groups"]) for q in questions)


def test_explain_matches_the_real_bootstrap_selection_and_names_reasons(tmp_path):
    from brain_eleven.runtime.context import compile_bootstrap, explain_bootstrap
    vault, _ = _runtime(tmp_path, shadow_accept=True)
    texts = ["We decided that SRT-00 is closed and shipped.", "We decided SRT-00 is closed and shipped now.",
             "We decided the holdout corpus-v2 gate stays red.", "We decided Phase 20 remains frozen.",
             "We decided the dashboard stays read-only.", "We decided to keep SQLite for storage.",
             "We decided the review queue expires after seven days."]
    from brain_eleven.memory import MemoryStore
    for i, text in enumerate(texts):
        _accept(vault, _review_item(tmp_path, vault, f"m{i}", text, NEW_TIME))
    ids = {m["content"]: m["memory_id"] for m in MemoryStore(vault).load()["validated_memory"]}
    delivered = set(compile_bootstrap(vault, vault)["selected_ids"])
    explained = explain_bootstrap(vault, vault)
    # Same steps as the real bootstrap: the explained DELIVERED set is exactly what it selects.
    assert {m for m, e in explained["memories"].items() if e["reason"] == "DELIVERED"} == delivered
    assert len(delivered) == 5 and -1 not in delivered
    # Scores tie here, so which twin ranks first varies; they are never delivered together.
    assert not {ids[texts[0]], ids[texts[1]]} <= delivered
    assert sum(explained["counts"].values()) == len(texts)
