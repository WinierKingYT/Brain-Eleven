"""Content fingerprints for the exact IG01-D public measurement inputs."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Iterable


_CODE_PATHS = (
    "evals/baseline.py",
    "evals/compiler_v2_provider.py",
    "evals/contracts.py",
    "evals/fixture_generator.py",
    "evals/metrics.py",
    "evals/reporting.py",
    "evals/run.py",
    "evals/schema.py",
    "evals/fixtures/phase15-contract.json",
    "scripts/context-compiler.py",
    "scripts/task_state_context.py",
    "scripts/memory_scope.py",
    "scripts/memory_store.py",
    "scripts/project_registry.py",
)


def _normalized_bytes(path: Path) -> bytes:
    return path.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")


def _framed_digest(root: Path, paths: Iterable[Path]) -> str:
    digest = hashlib.sha256()
    ordered = sorted(set(paths), key=lambda item: item.relative_to(root).as_posix())
    for path in ordered:
        relative = path.relative_to(root).as_posix().encode("utf-8")
        content = _normalized_bytes(path)
        digest.update(len(relative).to_bytes(4, "big"))
        digest.update(relative)
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
    return f"sha256:{digest.hexdigest()}"


def _public_paths(root: Path) -> tuple[Path, ...]:
    paths = [root / "manifest.json"]
    for split in ("dev", "test"):
        paths.extend(sorted((root / split).glob("p15_*.json")))
    if not all(path.is_file() for path in paths):
        missing = [path.relative_to(root).as_posix() for path in paths if not path.is_file()]
        raise ValueError(f"IG01-D public corpus is incomplete: {missing[:5]}")
    return tuple(paths)


def corpus_split_fingerprint(corpus_root: Path | str) -> str:
    """Hash manifest + DEV + VALIDATION, never reading HOLDOUT files."""

    root = Path(corpus_root).resolve()
    return _framed_digest(root, _public_paths(root))


def evaluation_source_fingerprint(root: Path | str, corpus_root: Path | str) -> str:
    """Hash executable measurement code and only the public corpus inputs."""

    source_root = Path(root).resolve()
    corpus = Path(corpus_root).resolve()
    paths = [source_root / relative for relative in _CODE_PATHS]
    paths.extend(_public_paths(corpus))
    if not all(path.is_file() for path in paths):
        missing = [str(path) for path in paths if not path.is_file()]
        raise ValueError(f"IG01-D source fingerprint input is missing: {missing[:5]}")
    digest = hashlib.sha256()
    for path in sorted(paths, key=lambda item: str(item).lower()):
        relative = (
            path.relative_to(source_root).as_posix()
            if path.is_relative_to(source_root)
            else f"corpus/{path.relative_to(corpus).as_posix()}"
        ).encode("utf-8")
        content = _normalized_bytes(path)
        digest.update(len(relative).to_bytes(4, "big"))
        digest.update(relative)
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
    return f"sha256:{digest.hexdigest()}"

