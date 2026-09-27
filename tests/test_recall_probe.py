"""Automated five-question recall probe over a real runtime vault."""

from brain_eleven.runtime import recall_probe
from brain_eleven.runtime.recall_probe import covers, probe
from tests.test_memclaim01_claim_key import NEW_TIME, _accept, _review_item, _runtime


def test_covers_needs_every_group_and_folds_turkish_case():
    groups = [["holdout", "corpus-v2"], ["kırmızı", "red"]]
    assert covers("Holdout kapısı KIRMIZI bırakıldı", groups)
    assert not covers("holdout gate stays", groups)
    # English capitals must not be Turkish-folded away ("I" -> "ı").
    q4 = [["phase 20"], ["frozen"], ["intelligence graduation"]]
    assert covers("Phase 20 frozen; aktif program Intelligence Graduation (IG).", q4)
    assert covers("PHASE 20: FROZEN. ACTIVE PROGRAM: INTELLIGENCE GRADUATION (IG).", q4)


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
    # Seven records, one near-duplicate twin: all six distinct ones fit in the slots.
    assert len(delivered) == 6 and -1 not in delivered
    # Scores tie here, so which twin ranks first varies; they are never delivered together.
    assert not {ids[texts[0]], ids[texts[1]]} <= delivered
    assert sum(explained["counts"].values()) == len(texts)


def test_answer_waiting_in_the_review_queue_is_pointed_at_and_surfaced(tmp_path):
    from fastapi.testclient import TestClient
    from brain_eleven.runtime.service import create_app
    vault, _ = _runtime(tmp_path, shadow_accept=True)
    pending = _review_item(tmp_path, vault, "q3",
                           "We decided not to push master because it publishes the ghcr latest image.", NEW_TIME)

    by_id = {r["id"]: r for r in probe(vault)["results"]}
    assert by_id[3]["status"] == "IN_REVIEW_QUEUE" and by_id[3]["review_ids"] == [pending["id"]]
    assert by_id[5]["status"] == "NOT_IN_MEMORY"

    client = TestClient(create_app(vault, token="t", background=False), base_url="http://127.0.0.1")
    listed = {x["id"]: x for x in client.get("/api/review/candidates", headers={"Authorization": "Bearer t"}).json()["candidates"]}
    assert listed[pending["id"]]["recall_questions"] == [3]

    _accept(vault, pending)
    assert {r["id"]: r for r in probe(vault)["results"]}[3]["status"] == "IN_CONTEXT"


def test_answer_split_across_two_pending_candidates_is_pointed_at_as_split(tmp_path):
    from fastapi.testclient import TestClient
    from brain_eleven.runtime.service import create_app
    vault, _ = _runtime(tmp_path, shadow_accept=True)
    first = _review_item(tmp_path, vault, "a", "We decided not to push master for now.", NEW_TIME)
    second = _review_item(tmp_path, vault, "b", "We decided that CI publishes the ghcr latest image.", NEW_TIME)
    _review_item(tmp_path, vault, "c", "We decided that the dashboard stays read-only.", NEW_TIME)

    entry = {r["id"]: r for r in probe(vault)["results"]}[3]
    assert entry["status"] == "IN_REVIEW_QUEUE" and entry["split"] is True
    assert sorted(entry["review_ids"]) == sorted([first["id"], second["id"]])

    client = TestClient(create_app(vault, token="t", background=False), base_url="http://127.0.0.1")
    listed = {x["id"]: x for x in client.get("/api/review/candidates", headers={"Authorization": "Bearer t"}).json()["candidates"]}
    assert listed[first["id"]]["recall_questions"] == [3] and listed[second["id"]]["recall_questions"] == [3]


def test_split_cover_needs_every_group():
    from brain_eleven.runtime.recall_probe import split_cover
    groups = [["master"], ["ghcr"], ["latest"]]
    assert split_cover([("a", "master"), ("b", "ghcr latest")], groups) == ["b", "a"]
    assert split_cover([("a", "master"), ("b", "ghcr")], groups) == []


def test_bootstrap_shows_a_long_decision_whole_up_to_the_limit(tmp_path):
    from brain_eleven.runtime.context import compile_bootstrap
    vault, _ = _runtime(tmp_path, shadow_accept=True)
    text = ("We decided that real sessions were dropped because the reader rejected unknown record types, "
            "and the fix skips and counts unknown types so the rest of the session is still captured.")
    assert 150 < len(text) < 400
    _accept(vault, _review_item(tmp_path, vault, "long", text, NEW_TIME))
    context = compile_bootstrap(vault, vault)["context"]
    assert text in context and text + "..." not in context


def test_in_context_needs_the_whole_answer_in_one_record(tmp_path, monkeypatch):
    from brain_eleven.runtime import recall_probe as rp
    context = ("## TOP MEMORIES\n\n1. [DECISION]\n   We decided not to push master for now.\n   Score: 0.9\n\n"
               "2. [DECISION]\n   CI publishes the ghcr latest image on every build.\n   Score: 0.9\n")
    groups = [["push"], ["ghcr", "image"]]
    assert rp.in_context(context, groups) == "SPLIT"
    assert rp.in_context(context.replace("for now", "because it publishes the ghcr image"), groups) == "WHOLE"
    assert rp.in_context("## TOP MEMORIES\n\n1. [DECISION]\n   nothing here\n", groups) is None


def test_cli_reads_a_local_questions_file(tmp_path, capsys):
    import json
    from brain_eleven.__main__ import main
    vault, _ = _runtime(tmp_path, shadow_accept=True)
    _accept(vault, _review_item(tmp_path, vault, "bandit",
                                "We decided to use the repo nosec rule and the gate stays unchanged.", NEW_TIME))
    local = tmp_path / "questions-local.json"
    # Windows PowerShell 5 Set-Content -Encoding utf8 writes a BOM.
    local.write_text(json.dumps({"questions": [
        {"id": 1, "question": "Bandit?", "groups": [["nosec"], ["gate"]]}]}), encoding="utf-8-sig")
    main(["--vault", str(vault), "recall-probe", "--questions", str(local)])
    result = json.loads(capsys.readouterr().out)
    assert (result["score"], result["of"]) == (1, 1)
