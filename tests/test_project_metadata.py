"""Project metadata must describe the environment used by production and tests."""

from __future__ import annotations

from pathlib import Path
import tomllib


ROOT = Path(__file__).resolve().parents[1]


def test_pyproject_runtime_dependencies_match_pinned_requirements() -> None:
    metadata = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    requirements = {
        line.strip()
        for line in (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }

    assert metadata["project"]["requires-python"] == ">=3.11"
    assert set(metadata["project"]["dependencies"]) == requirements
