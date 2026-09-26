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
