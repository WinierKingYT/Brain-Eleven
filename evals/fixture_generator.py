"""Build deterministic, synthetic vaults for offline evaluation.

The generator intentionally does not import production retrieval code. It emits
the minimal canonical JSON envelope that the baseline adapter will later read,
while retaining stable fixture identities and repeatable ranking attributes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import tempfile
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Optional, Sequence

from .schema import FixtureMemory, VaultFixture, load_fixture


FIXTURE_MANIFEST_NAME = ".eval-fixture.json"
CANONICAL_MEMORY_RELATIVE_PATH = Path(".claude") / "validated-memory.json"
CANONICAL_SCHEMA_VERSION = 2
FIXTURE_GENERATOR_VERSION = 1
_EPOCH = datetime(2026, 1, 1, tzinfo=timezone.utc)


class FixtureGenerationError(ValueError):
    """Raised when generation would be non-deterministic or overwrite a vault."""


@dataclass(frozen=True)
class GeneratedVault:
    """Stable metadata describing one generated synthetic vault."""

    root: Path
    fixture_id: str
    seed: int
    memory_ids: tuple[str, ...]
    noise_count: int


def _validate_seed(seed: int) -> None:
    if isinstance(seed, bool) or not isinstance(seed, int) or seed < 0:
        raise FixtureGenerationError("seed must be a non-negative integer")


def _validate_noise_count(noise_count: int) -> None:
    if isinstance(noise_count, bool) or not isinstance(noise_count, int) or noise_count < 0:
        raise FixtureGenerationError("noise_count must be a non-negative integer")


def _timestamp(seed: int, index: int) -> str:
    return (_EPOCH + timedelta(seconds=(seed * 1000) + index)).isoformat()


def _fingerprint(memory_type: str, content: str, scope: str, project_id: Optional[str]) -> str:
    namespace = project_id if scope == "project" else "global"
    payload = f"{namespace}\x1f{memory_type}\x1f{content}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def make_memory(memory: FixtureMemory, *, seed: int, index: int, quality: float) -> dict[str, Any]:
    """Convert one fixture label into a canonical-memory-shaped synthetic record."""

    project_id = memory.project_id or ""
    return {
        "memory_id": memory.memory_id,
        "type": memory.memory_type,
        "content": memory.content,
        "confidence": quality,
        "quality_score": quality,
        "source": "eval_fixture",
        "timestamp": _timestamp(seed, index),
        "related_notes": [],
        "section": "Phase 15 synthetic fixture",
        "issues": [],
        "novelty": 1.0,
        "is_approved": True,
        "status": memory.status,
        "resolved_at": "",
        "resolved_by": "",
        "resolution_note": "",
        "superseded_by": "",
        "supersession_note": "",
        "dedup_fingerprint": _fingerprint(
            memory.memory_type,
            memory.content,
            memory.scope,
            memory.project_id,
        ),
        "scope": memory.scope,
        "project": project_id,
        "project_label": project_id,
        "project_id": project_id,
    }


def _noise_memories(fixture: VaultFixture, seed: int, count: int) -> Iterable[FixtureMemory]:
    project_ids = tuple(sorted(fixture.project_ids))
    for index in range(count):
        scope = "global" if index % 3 == 0 or not project_ids else "project"
        project_id = None if scope == "global" else project_ids[index % len(project_ids)]
        yield FixtureMemory(
            memory_id=f"noise_{seed}_{index:04d}",
            memory_type="observation",
            status="active",
            content=f"Synthetic irrelevant evaluation noise {seed}-{index}.",
            scope=scope,
            project_id=project_id,
        )


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Optional[Path] = None
    try:
        descriptor, temporary_name = tempfile.mkstemp(
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
        )
        temporary_path = Path(temporary_name)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True, ensure_ascii=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        temporary_path.replace(path)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()


def _ensure_empty_target(target: Path) -> None:
    if target.is_symlink():
        raise FixtureGenerationError(f"target must not be a symlink: {target}")
    if target.exists() and not target.is_dir():
        raise FixtureGenerationError(f"target is not a directory: {target}")
    if target.exists() and any(target.iterdir()):
        raise FixtureGenerationError(f"refusing to overwrite non-empty target: {target}")


def build_vault(
    fixture: VaultFixture,
    target: Path | str,
    *,
    seed: int = 0,
    noise_count: int = 0,
) -> GeneratedVault:
    """Build one safe, deterministic synthetic vault in an empty target directory."""

    _validate_seed(seed)
    _validate_noise_count(noise_count)
    root = Path(target)
    created_root = not root.exists()
    _ensure_empty_target(root)
    root.mkdir(parents=True, exist_ok=True)

    rng = random.Random(seed)
    fixture_memories = tuple(fixture.memories[memory_id] for memory_id in sorted(fixture.memories))
    all_memories = fixture_memories + tuple(_noise_memories(fixture, seed, noise_count))
    records = [
        make_memory(
            memory,
            seed=seed,
            index=index,
            quality=round(0.55 + (rng.random() * 0.35), 6),
        )
        for index, memory in enumerate(all_memories)
    ]

    generated_at = _timestamp(seed, len(records))
    canonical = {
        "schema_version": CANONICAL_SCHEMA_VERSION,
        "revision": 0,
        "updated_at": generated_at,
        "validated_at": generated_at,
        "summary": {
            "source": "phase15_synthetic_fixture",
            "fixture_id": fixture.fixture_id,
            "seed": seed,
            "noise_count": noise_count,
        },
        "validated_memory": records,
        "rejected_memory": [],
    }
    manifest = {
        "schema_version": 1,
        "generator_version": FIXTURE_GENERATOR_VERSION,
        "fixture_id": fixture.fixture_id,
        "seed": seed,
        "noise_count": noise_count,
        "memory_ids": [record["memory_id"] for record in records],
        "generated_at": generated_at,
    }
    try:
        _atomic_write_json(root / CANONICAL_MEMORY_RELATIVE_PATH, canonical)
        _atomic_write_json(root / FIXTURE_MANIFEST_NAME, manifest)
    except Exception:
        # Remove only paths created by this call. An empty target may have
        # existed before invocation and must remain under the caller's control.
        canonical_path = root / CANONICAL_MEMORY_RELATIVE_PATH
        canonical_path.unlink(missing_ok=True)
        (root / FIXTURE_MANIFEST_NAME).unlink(missing_ok=True)
        if canonical_path.parent.exists() and not any(canonical_path.parent.iterdir()):
            canonical_path.parent.rmdir()
        if created_root and root.exists() and not any(root.iterdir()):
            root.rmdir()
        raise

    return GeneratedVault(
        root=root,
        fixture_id=fixture.fixture_id,
        seed=seed,
        memory_ids=tuple(record["memory_id"] for record in records),
        noise_count=noise_count,
    )


def build_vault_from_path(
    fixture_path: Path | str,
    target: Path | str,
    *,
    seed: int = 0,
    noise_count: int = 0,
) -> GeneratedVault:
    """Load a versioned fixture document, then create its synthetic vault."""

    return build_vault(load_fixture(fixture_path), target, seed=seed, noise_count=noise_count)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Build a deterministic Brain-Eleven evaluation vault.")
    parser.add_argument("fixture", type=Path, help="Synthetic fixture JSON path")
    parser.add_argument("target", type=Path, help="New or empty output directory")
    parser.add_argument("--seed", type=int, default=0, help="Non-negative deterministic seed")
    parser.add_argument("--noise-count", type=int, default=0, help="Number of synthetic irrelevant memories")
    args = parser.parse_args(argv)

    try:
        generated = build_vault_from_path(
            args.fixture,
            args.target,
            seed=args.seed,
            noise_count=args.noise_count,
        )
    except FixtureGenerationError as error:
        parser.error(str(error))
    print(
        json.dumps(
            {
                "fixture_id": generated.fixture_id,
                "seed": generated.seed,
                "noise_count": generated.noise_count,
                "memory_count": len(generated.memory_ids),
                "target": str(generated.root),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
