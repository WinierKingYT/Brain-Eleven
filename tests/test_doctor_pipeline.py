"""doctor's pipeline view: queue, last capture, review backlog, measurement."""

import json

from brain_eleven.runtime.install import _pipeline_health
from brain_eleven.runtime.storage import RuntimeConfig, write_json


def test_pipeline_health_counts_and_suggests_next_steps(tmp_path):
    vault = tmp_path
    cfg = RuntimeConfig(vault)
    cfg.ensure_root()
    dead = vault / ".brain-eleven" / "capture" / "dead-letter"
    dead.mkdir(parents=True)
    (dead / "cap_1.json").write_text(json.dumps({"last_error_code": "UNSUPPORTED_CODEX_TRANSCRIPT"}), encoding="utf-8")
    (dead / "cap_2.json").write_text(json.dumps({"last_error_code": "TRANSCRIPT_OWNERSHIP_UNVERIFIED"}), encoding="utf-8")
    write_json(cfg.root / "last-capture-codex.json",
               {"at": "2026-09-26T09:00:00+00:00", "event": "Stop", "outcome": "CWD_NOT_REGISTERED", "error": None})
    for i, status in enumerate(["PENDING", "PENDING", "REJECTED"]):
        write_json(cfg.root / "review" / f"rev_{i:064x}.json", {"status": status})

    health = _pipeline_health(vault, cfg)

    assert health["capture_queue"]["dead-letter"] == 2
    assert health["capture_queue"]["dead_letter_by_code"] == {
        "UNSUPPORTED_CODEX_TRANSCRIPT": 1, "TRANSCRIPT_OWNERSHIP_UNVERIFIED": 1}
    assert health["last_capture"]["codex"]["outcome"] == "CWD_NOT_REGISTERED"
    assert health["review_pending"] == 2
    assert health["last_measurement"] is None
    joined = " | ".join(health["suggestions"])
    assert "1 dead-lettered capture(s) are retryable" in joined
    assert "codex capture was CWD_NOT_REGISTERED" in joined
    assert "python -m brain_eleven measure" in joined

    write_json(cfg.root / "measurements" / "20260929T070000Z.json",
               {"measured_at": "2026-09-29T07:00:00+00:00", "capture": {"verdict": "PASS"}})
    assert _pipeline_health(vault, cfg)["last_measurement"] == {"at": "2026-09-29T07:00:00+00:00", "capture_verdict": "PASS"}


def test_bom_in_codex_hooks_is_flagged_and_install_rewrites_it_without_bom(tmp_path):
    from brain_eleven.runtime.install import client_file_state, doctor
    from brain_eleven.runtime.storage import read_json

    home = tmp_path / "home"
    (home / ".codex").mkdir(parents=True)
    hooks = home / ".codex" / "hooks.json"
    # What Windows PowerShell 5.1 `Set-Content -Encoding utf8` produced on the owner's machine.
    hooks.write_bytes(b"\xef\xbb\xbf" + json.dumps({"hooks": {}}).encode("utf-8"))
    assert client_file_state(hooks) == "BOM"
    assert read_json(hooks) == {"hooks": {}}  # our reader tolerates it

    vault = tmp_path / "vault"
    vault.mkdir()
    checks = doctor(vault, home=home)
    assert checks["clients"]["codex"]["file"] == "BOM"
    assert checks["clients"]["codex"]["configured"] is False
    assert any("codex hook file" in s and "BOM" in s for s in checks["suggestions"])

    write_json(hooks, read_json(hooks))  # what install does when it rewrites the file
    assert not hooks.read_bytes().startswith(b"\xef\xbb\xbf")
    assert client_file_state(hooks) == "OK"
