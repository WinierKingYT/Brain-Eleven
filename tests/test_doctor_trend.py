"""doctor shows a 7-day measurement trend and flags a recall or capture regression."""

from datetime import datetime, timedelta, timezone

from brain_eleven.runtime.install import _pipeline_health, measurement_trend
from brain_eleven.runtime.storage import RuntimeConfig, write_json
from tests.test_memclaim01_claim_key import _runtime


def _save(vault, name, at, score, missing):
    write_json(RuntimeConfig(vault).root / "measurements" / f"{name}.json",
               {"measured_at": at.isoformat(), "recall_probe": {"score": score},
                "capture": {"verdict": "FAIL", "totals": {"sessions": 5, "missing": missing, "dead_letter": 0}}})


def test_trend_keeps_last_seven_days_oldest_first_and_flags_drops(tmp_path):
    vault, _ = _runtime(tmp_path, shadow_accept=True)
    now = datetime.now(timezone.utc)
    _save(vault, "a", now - timedelta(days=10), 5, 0)
    _save(vault, "b", now - timedelta(days=3), 3, 0)
    _save(vault, "c", now - timedelta(days=1), 2, 2)

    cfg = RuntimeConfig(vault)
    trend = measurement_trend(sorted((cfg.root / "measurements").glob("*.json")))
    assert [t["recall_score"] for t in trend] == [3, 2]

    health = _pipeline_health(vault, cfg, tmp_path / "home")
    assert len(health["measurement_trend"]) == 2
    assert any("recall score dropped to 2" in s for s in health["suggestions"])
    assert any("capture misses grew" in s for s in health["suggestions"])


def test_trend_is_quiet_when_stable(tmp_path):
    vault, _ = _runtime(tmp_path, shadow_accept=True)
    now = datetime.now(timezone.utc)
    _save(vault, "a", now - timedelta(days=2), 1, 0)
    _save(vault, "b", now - timedelta(days=1), 2, 0)
    health = _pipeline_health(vault, RuntimeConfig(vault), tmp_path / "home")
    assert not any("dropped" in s or "grew" in s for s in health["suggestions"])
