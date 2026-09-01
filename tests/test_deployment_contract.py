"""Static contracts for the local-only Docker deployment boundary."""

from pathlib import Path


ROOT = Path(__file__).parent.parent


def test_healthchecks_use_only_python_standard_library():
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")

    assert "from urllib.request import urlopen" in dockerfile
    assert "import requests" not in dockerfile
    assert 'test: ["CMD", "python", "-c", "from urllib.request import urlopen' in compose
    assert '"curl", "-f"' not in compose


def test_compose_publishes_services_to_loopback_only():
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")

    for mapping in ("127.0.0.1:8000:8000", "127.0.0.1:6379:6379", "127.0.0.1:5432:5432"):
        assert mapping in compose
