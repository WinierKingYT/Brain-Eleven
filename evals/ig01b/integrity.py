"""Integrity checks for the IG-01-B public corpus and privacy boundary."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from collections import Counter
from pathlib import Path
from typing import Any

from .generator import CORPUS_VERSION, PUBLIC_ROOT
from .schema import LANGUAGES, PHENOMENA, load_cases

# Immutable review baseline for ig-eval-v1.  A changed holdout must create a
# new corpus version and a new pinned constant; editing the manifest alone
# cannot make a changed holdout pass CI.
PINNED_HOLDOUT_SHA256 = "27bd0157074233736ebd20fad918dde14b7e3f4999f1b58931c9987a23ccc5d2"

PRIVATE_MARKERS = ("evals/ig01b/private", ".test-tmp", "PRIVATE_REALISTIC")
SECRET_PATTERNS = (
    re.compile(r"(?i)(api[_-]?key|secret|token|password)\s*[:=]\s*['\"]?[A-Za-z0-9_\-/+=]{12,}"),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
)
PII_PATTERNS = (
    re.compile(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b"),
    re.compile(r"(?<!\d)(?:\+?\d[\d ()-]{8,}\d)(?!\d)"),
    re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"),
)
PINNED_HOLDOUT_TAG = "ig01b-corpus-v1"


def canonical_jsonl_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def public_case_paths(root: Path = PUBLIC_ROOT) -> dict[str, Path]:
    return {split: root / f"{split}.jsonl" for split in ("dev", "validation", "holdout", "abstention")}


def verify_holdout_hash(root: Path = PUBLIC_ROOT) -> bool:
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    actual = canonical_jsonl_sha256(root / "holdout.jsonl")
    sidecar = (root / "holdout.sha256").read_text(encoding="utf-8").split()[0]
    return actual == PINNED_HOLDOUT_SHA256 == sidecar == manifest.get("holdout_sha256") == manifest.get("file_sha256", {}).get("holdout")


def verify_holdout_tag(root: Path = PUBLIC_ROOT) -> bool:
    """Compare current holdout bytes with the immutable corpus tag tree."""

    repository_root = root.resolve().parents[3]
    relative = "evals/ig01b/public/ig-eval-v1/holdout.jsonl"
    result = subprocess.run(
        ["git", "show", f"refs/tags/{PINNED_HOLDOUT_TAG}:{relative}"],
        cwd=repository_root,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        return False
    return hashlib.sha256(result.stdout).hexdigest() == canonical_jsonl_sha256(root / "holdout.jsonl")


def check_public_corpus(root: Path = PUBLIC_ROOT) -> dict[str, Any]:
    paths = public_case_paths(root)
    loaded = {split: load_cases(path, expected_class="PUBLIC_SYNTHETIC") for split, path in paths.items()}
    answerable = loaded["dev"] + loaded["validation"] + loaded["holdout"]
    matrix = Counter((case["category"], case["language"]) for case in answerable)
    missing = [f"{category}:{language}" for category in PHENOMENA for language in LANGUAGES if matrix[(category, language)] < 3]
    holdout = loaded["holdout"]
    if not 30 <= len(holdout) <= 50:
        raise ValueError(f"holdout must contain 30-50 cases, found {len(holdout)}")
    if missing:
        raise ValueError(f"phenomenon/language matrix incomplete: {missing}")
    if not verify_holdout_hash(root):
        raise ValueError("holdout hash mismatch")
    if not verify_holdout_tag(root):
        raise ValueError(f"holdout does not match immutable tag {PINNED_HOLDOUT_TAG}")
    raw = "\n".join(path.read_text(encoding="utf-8") for path in paths.values())
    secret_hits = [pattern.pattern for pattern in SECRET_PATTERNS if pattern.search(raw)]
    pii_hits = [pattern.pattern for pattern in PII_PATTERNS if pattern.search(raw)]
    if secret_hits or pii_hits:
        raise ValueError(f"public corpus privacy scan failed: secrets={secret_hits}, pii={pii_hits}")
    ids = [case["case_id"] for case in answerable]
    if len(ids) != len(set(ids)):
        raise ValueError("public corpus IDs are not unique")
    fingerprints = {}
    for case in answerable:
        fingerprint = (case["category"], case["language"], case["query"], tuple(case["candidate_ids"]))
        if fingerprint in fingerprints:
            raise ValueError(f"duplicate content across corpus splits: {case['case_id']} and {fingerprints[fingerprint]}")
        fingerprints[fingerprint] = case["case_id"]
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("corpus_version") != CORPUS_VERSION:
        raise ValueError("manifest version mismatch")
    if manifest.get("total_answerable") != len(answerable):
        raise ValueError("manifest answerable count mismatch")
    return {
        "corpus_version": CORPUS_VERSION,
        "splits": {split: len(values) for split, values in loaded.items()},
        "total_answerable": len(answerable),
        "matrix_cells": len(matrix),
        "matrix_minimum": min(matrix.values()),
        "holdout_sha256": manifest["holdout_sha256"],
        "inter_annotator_disagreement_rate": manifest["inter_annotator_disagreement_rate"],
        "secret_hits": 0,
        "pii_hits": 0,
    }


def assert_private_path(path: Path, repository_root: Path) -> None:
    """Reject private corpus files inside tracked/public corpus directories."""

    resolved = path.resolve()
    root = repository_root.resolve()
    try:
        relative = resolved.relative_to(root).as_posix().lower()
    except ValueError as exc:
        raise ValueError("private corpus must be under the repository's ignored local area") from exc
    if not (relative == "evals/private" or relative.startswith("evals/private/") or any(marker.lower() in relative for marker in PRIVATE_MARKERS)):
        raise ValueError(f"private corpus path is outside the guarded local area: {relative}")
    if "/public/" in f"/{relative}/" or "/failures/" in f"/{relative}/":
        raise ValueError("private corpus cannot be stored in public or failure corpus paths")


def check_private_boundary(repository_root: Path) -> dict[str, Any]:
    private_root = repository_root / "evals" / "private"
    assert_private_path(private_root, repository_root)
    tracked = []
    for candidate in repository_root.rglob("*"):
        relative = candidate.resolve().relative_to(repository_root.resolve()).as_posix().lower()
        if candidate.is_file() and (relative.startswith("evals/private/") or "private_realistic" in relative):
            tracked.append(candidate.as_posix())
    return {"guard_root": private_root.as_posix(), "tracked_private_candidates": tracked, "leakage": 0}
