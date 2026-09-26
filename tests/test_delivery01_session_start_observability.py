"""DELIVERY-01 native SessionStart observability regression tests."""

from __future__ import annotations

from brain_eleven.runtime.install import _session_start_health
from brain_eleven.runtime.storage import RuntimeConfig, identity, write_json


def test_native_session_start_receipt_is_visible_without_legacy_breadcrumb(tmp_path):
    cfg = RuntimeConfig(tmp_path)
    cfg.ensure_root()
    write_json(
        cfg.root / "deliveries" / "delivery.json",
        {
            "status": "EMITTED",
            "at": "2026-09-24T10:11:12+00:00",
            "client": "codex",
            "event": "SessionStart",
            "context_delivered": True,
        },
    )

    message, failed = _session_start_health(tmp_path)

    assert message == "last SessionStart: ok at 2026-09-24T10:11:12+00:00 (native; context delivered)"
    assert failed is False


def test_pre_event_native_bootstrap_receipt_remains_observable(tmp_path):
    cfg = RuntimeConfig(tmp_path)
    cfg.ensure_root()
    write_json(
        cfg.root / "deliveries" / "legacy-native-delivery.json",
        {
            "status": "EMITTED",
            "at": "2026-09-24T10:11:12+00:00",
            "client": "claude",
            "turn_hash": identity("turn_", "bootstrap"),
            "context_delivered": False,
        },
    )

    message, failed = _session_start_health(tmp_path)

    assert message == "last SessionStart: ok at 2026-09-24T10:11:12+00:00 (native; context empty)"
    assert failed is False


def test_non_session_start_delivery_does_not_claim_session_health(tmp_path):
    cfg = RuntimeConfig(tmp_path)
    cfg.ensure_root()
    write_json(
        cfg.root / "deliveries" / "prompt-delivery.json",
        {
            "status": "EMITTED",
            "at": "2026-09-24T10:11:12+00:00",
            "client": "codex",
            "event": "UserPromptSubmit",
            "context_delivered": True,
        },
    )

    assert _session_start_health(tmp_path) == ("last SessionStart: unknown", False)


def test_doctor_surfaces_native_session_start_receipt(tmp_path, monkeypatch):
    from brain_eleven.runtime import install, launcher

    cfg = RuntimeConfig(tmp_path)
    cfg.ensure_root()
    write_json(
        cfg.root / "deliveries" / "delivery.json",
        {
            "status": "EMITTED",
            "at": "2026-09-24T10:11:12+00:00",
            "client": "codex",
            "event": "SessionStart",
            "context_delivered": True,
        },
    )
    monkeypatch.setattr(install, "client_paths", lambda home=None: {})
    monkeypatch.setattr(launcher, "request_service", lambda *_args, **_kwargs: {"status": "ok"})

    checks = install.doctor(tmp_path)

    assert checks["last_session_start"].endswith("(native; context delivered)")
    assert checks["status"] == "READY"
