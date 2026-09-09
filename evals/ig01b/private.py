"""Local-only PRIVATE_REALISTIC corpus storage with repository path guards."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .integrity import assert_private_path
from .schema import validate_case

_RAW_KEYS = frozenset({"prompt", "transcript", "raw_text", "memory_content", "token", "secret", "password", "query"})


def _assert_content_free(value: Any, path: str = "case") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if str(key).lower() in _RAW_KEYS:
                raise ValueError(f"private realistic data contains forbidden raw field: {path}.{key}")
            _assert_content_free(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _assert_content_free(child, f"{path}[{index}]")


def private_root(repository_root: Path) -> Path:
    root = (repository_root / "evals" / "private").resolve()
    assert_private_path(root, repository_root)
    root.mkdir(parents=True, exist_ok=True)
    return root


def write_private_case(repository_root: Path, case: dict[str, Any]) -> Path:
    """Write sanitized local data only; callers must remove raw prompt content."""

    if case.get("dataset_class") != "PRIVATE_REALISTIC":
        raise ValueError("private case must declare dataset_class=PRIVATE_REALISTIC")
    _assert_content_free(case)
    validate_case(case)
    root = private_root(repository_root)
    case_id = case.get("case_id")
    if not isinstance(case_id, str) or not case_id or any(char in case_id for char in "/\\"):
        raise ValueError("private case_id must be a safe filename component")
    path = root / f"{case_id}.json"
    assert_private_path(path, repository_root)
    path.write_text(json.dumps(case, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def repository_leak_candidates(repository_root: Path) -> list[Path]:
    """Return files that would be a private-corpus leak if tracked or public."""

    candidates: list[Path] = []
    for path in repository_root.rglob("*"):
        if not path.is_file():
            continue
        lowered = path.as_posix().lower()
        if "private_realistic" in lowered or "/evals/private/" in lowered:
            candidates.append(path)
    return candidates
