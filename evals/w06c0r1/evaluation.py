"""W-06C0R1 evaluation-only corpus and provider-parity harness.

The evaluator owns the corpus/provenance boundary.  Provider code receives an
opaque task handle and an isolated synthetic vault, never public case IDs,
labels, attestations, or expected memory IDs.
"""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import math
import re
import statistics
import subprocess
import sys
import tempfile
import unicodedata
from pathlib import Path
from time import perf_counter
from typing import Any, Iterable, Mapping, Sequence

from brain_eleven.retrieval import EmbeddingStatus, create_embedding_provider, create_reranker
from context_compiler_v2.safety import contains_secret
from context_compiler_v2.tokenizer import ConservativeTokenEstimator
from evals.authority_provider import AuthorityContextProvider
from evals.baseline import BaselineContextProvider, TaskAwareV1ContextProvider
from evals.compiler_v2_provider import CompilerV2ContextProvider
from evals.contracts import NormalizedEvaluationResult, SelectedContextItem
from evals.fixture_generator import build_vault
from evals.schema import GoldenTask, load_fixture, parse_task


ROOT = Path(__file__).resolve().parents[2]
CORPUS_ROOT = ROOT / "evals" / "corpus-v4"
FIXTURE_PATH = ROOT / "evals" / "fixtures" / "phase15-contract.json"
FINAL_HOLDOUT_OUTPUT = ROOT / "evals" / "w06c0r1" / "evidence" / "holdout.json"
HISTORICAL_SCOPE_COMPAT_METADATA = ROOT / "evals" / "w06c0r1" / "historical_scope_compat.json"
HISTORICAL_SCOPE_COMPAT_ID = "W06C0-SCOPE-COMPAT-P1B"
HISTORICAL_SCOPE_COMPAT_SCOPE_END_REVISION = "f676c91d0e41a7523dc2b96a131814b983401456"
HISTORICAL_SCOPE_COMPAT_BLOB_SHA256 = "sha256:e375d337a52155d867c12b2f334c56ecf0875d1d153cb99a48980230ae05b3be"
IMPLEMENTATION_SCOPE_END_REVISION = "0b5a262c437da13813e542c569857a68c2db7a69"
SCOPE_DRIFT_PIN = ROOT / "WEAKNESS-W06C0R1-SCOPE-DRIFT-PIN-R3.json"
SCOPE_DRIFT_PIN_RELATIVE = "WEAKNESS-W06C0R1-SCOPE-DRIFT-PIN-R3.json"
SCOPE_DRIFT_HISTORICAL_PIN_RELATIVE = frozenset(
    {
        "WEAKNESS-W06C0R1-SCOPE-DRIFT-PIN.json",
        "WEAKNESS-W06C0R1-SCOPE-DRIFT-PIN-R2.json",
    }
)
SCOPE_DRIFT_PIN_ID = "W06C0R1-SCOPE-DRIFT-P3"
SCOPE_DRIFT_MAINTENANCE_FILES = frozenset(
    {
        "evals/corpus-v4/manifest.json",
        "evals/corpus-v4/holdout/seal.json",
        "evals/w06c0r1/evaluation.py",
        "evals/w06c0r1/evidence/dev.json",
        "evals/w06c0r1/evidence/test.json",
        "evals/w06c0r1/evidence/holdout.json",
        "tests/test_w06c0r1_contract.py",
        "WEAKNESS-W06C0R1-SCOPE-DRIFT-PIN.json",
        "WEAKNESS-W06C0R1-SCOPE-DRIFT-PIN-R2.json",
        "WEAKNESS-W06C0R1-SCOPE-DRIFT-PIN-R3.json",
    }
)
SCOPE_DRIFT_DOCUMENTATION_FILES = frozenset(
    {
        "WEAKNESS-W06C0R1-SCOPE-DRIFT-CONTRACT.md",
        "WEAKNESS-W06C0R1-SCOPE-DRIFT-PACKAGE-REPORT.md",
        "WEAKNESS-W06C0R1-SCOPE-DRIFT-INDEPENDENT-REVIEW.md",
        "ENGINEERING-WEAK-POINTS-AUDIT.md",
    }
)
POST_SCOPE_PROTECTED_PREFIXES = (
    "evals/w06c0r1/",
    "evals/corpus-v4/",
    "evals/w06c0/",
    "tests/test_w06c0r1_",
)
EVALUATOR_VERSION = "w06c0r1-v1"
CORPUS_VERSION = 4
PROVENANCE_VERSION = "w06c0r1-provenance-v1"
ANSWERABILITY_STATUSES = frozenset({"answerable", "unanswerable", "review_required"})
ANSWERABILITY_REASONS = frozenset(
    {
        "query_and_candidate_metadata_support_target",
        "query_lacks_target_discriminator",
        "gold_label_depends_on_hidden_fixture_metadata",
        "candidate_snapshot_incomplete",
        "annotation_disagreement",
        "privacy_or_schema_review",
    }
)
SPLITS = ("dev", "test", "holdout")
SUITE_COUNTS = {"dev": 60, "test": 60, "holdout": 30}
MINIMUM_ANSWERABLE = {"dev": 45, "test": 45, "holdout": 22}
PHENOMENA = (
    "exact_relevant_memory",
    "paraphrase",
    "old_critical_decision",
    "current_state_or_blocker",
    "related_lesson",
    "recent_irrelevant_distractor",
    "same_keyword_wrong_meaning",
    "superseded_or_resolved_distractor",
    "cross_project_distractor",
)
K_VALUES = (1, 3, 5, 10)
PROVIDER_SLOTS = ("v1", "w06b", "v2", "authority_lexical", "embedding", "reranker")
CORE_PROVIDERS = PROVIDER_SLOTS[:4]
SEED = 17
NOISE_COUNT = 24
# The authorization note is a repository commit, so the machine scope gate
# starts after it; otherwise the gate would misclassify that pre-package note
# as an implementation change.
IMPLEMENTATION_BASE_REVISION = "3f795f9"
EVAL_SOURCE_PREFIXES = ("evals/w06c0r1/", "tests/test_w06c0r1_")
ALLOWED_SCOPE_PREFIXES = (
    "evals/corpus-v4/",
    "evals/w06c0r1/",
    "tests/test_w06c0r1_",
)
ALLOWED_SCOPE_FILES = frozenset(
    {
        "WEAKNESS-W06C0R1-CONTRACT-INDEPENDENT-REVIEW.md",
        "WEAKNESS-W06C0R1-HOLDOUT-REPLAY-FIX-CONTRACT.md",
        "WEAKNESS-W06C0R1-PACKAGE-REPORT.md",
        "WEAKNESS-W06C0-SCOPE-COMPAT-CONTRACT.md",
        "WEAKNESS-W06C0-REMEDIATION-CONTRACT-INDEPENDENT-REVIEW.md",
    }
)
FORBIDDEN_SCOPE_PREFIXES = (
    "brain_eleven/",
    "scripts/",
    "context_compiler_v2/",
    "authority/",
    "context_router/",
    ".claude/",
    "evals/corpus-v2/",
    "evals/corpus-v3/",
    "evals/w06c0/",
    "evals/w09a/",
    "evals/ig01c/",
)


class W06C0R1Error(ValueError):
    """Raised when the W-06C0R1 evidence boundary is invalid."""


def _text(value: str) -> str:
    return unicodedata.normalize("NFC", value.replace("\r\n", "\n").replace("\r", "\n"))


def _normalized(value: Any) -> Any:
    if isinstance(value, str):
        return _text(value)
    if isinstance(value, list):
        return [_normalized(item) for item in value]
    if isinstance(value, dict):
        return {str(_normalized(key)): _normalized(item) for key, item in value.items()}
    return value


def _canonical(value: Any) -> bytes:
    return json.dumps(
        _normalized(value), ensure_ascii=True, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def _sha(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _frame(value: bytes | str) -> bytes:
    data = value if isinstance(value, bytes) else _text(value).encode("utf-8")
    return len(data).to_bytes(8, "big") + data


def _normalized_bytes(path: Path) -> bytes:
    return path.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")


def _manifest_hash(manifest: Mapping[str, Any]) -> str:
    value = dict(manifest)
    value.pop("manifest_hash", None)
    return _sha(_canonical(value))


def _case_payload_hash(case: Mapping[str, Any]) -> str:
    value = json.loads(json.dumps(case))
    answerability = value.get("answerability")
    if not isinstance(answerability, dict):
        raise W06C0R1Error("case answerability is invalid")
    answerability.pop("case_payload_hash", None)
    answerability.pop("attestation_hash", None)
    return _sha(_canonical(value))


def _attestation_hash(attestation: Mapping[str, Any]) -> str:
    value = dict(attestation)
    value.pop("attestation_hash", None)
    return _sha(_canonical(value))


def _load_json(path: Path, error: str) -> Mapping[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise W06C0R1Error(error) from exc
    if not isinstance(value, Mapping):
        raise W06C0R1Error(error)
    return value


def _git_changed_paths(root: Path, *revisions: str) -> tuple[str, ...]:
    """Return normalized tracked paths changed by a git diff expression."""

    try:
        completed = subprocess.run(
            [
                "git",
                "-C",
                str(root),
                "diff",
                "--name-only",
                "--diff-filter=ACDMRTUXB",
                *revisions,
                "--",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise W06C0R1Error("cannot inspect exact scope diff") from exc
    return tuple(sorted({line.replace("\\", "/") for line in completed.stdout.splitlines() if line.strip()}))


def _resolve_revision(root: Path, revision: str, label: str) -> str:
    try:
        resolved = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--verify", f"{revision}^{{commit}}"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError) as exc:
        raise W06C0R1Error(f"cannot resolve {label} revision") from exc
    if not re.fullmatch(r"[0-9a-f]{40}", resolved):
        raise W06C0R1Error(f"{label} revision could not be resolved")
    return resolved


def _require_ancestor(root: Path, earlier: str, later: str, label: str) -> None:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "merge-base", "--is-ancestor", earlier, later],
            check=False,
            capture_output=True,
        )
    except OSError as exc:
        raise W06C0R1Error(f"cannot verify {label} revision ancestry") from exc
    if result.returncode != 0:
        raise W06C0R1Error(f"{label} revision is not an ancestor")


def _file_sha(path: Path, error: str) -> str:
    if path.is_symlink() or not path.is_file():
        raise W06C0R1Error(error)
    try:
        return _sha(_normalized_bytes(path))
    except OSError as exc:
        raise W06C0R1Error(error) from exc


def _git_pin_anchor_revision(root: Path, scope_end_revision: str) -> str:
    """Resolve the immutable first commit that introduced the scope pin."""

    try:
        completed = subprocess.run(
            [
                "git",
                "-C",
                str(root),
                "log",
                "--reverse",
                "--format=%H",
                f"{scope_end_revision}..HEAD",
                "--",
                SCOPE_DRIFT_PIN_RELATIVE,
            ],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise W06C0R1Error("cannot resolve scope drift pin anchor") from exc
    revisions = [line.strip() for line in completed.stdout.splitlines() if line.strip()]
    if not revisions or not re.fullmatch(r"[0-9a-f]{40}", revisions[0]):
        raise W06C0R1Error("scope drift pin anchor is missing or invalid")
    return revisions[0]


def _git_blob_sha(root: Path, revision: str, relative: str) -> str:
    """Return a normalized SHA for a tracked blob at an immutable revision."""

    try:
        completed = subprocess.run(
            ["git", "-C", str(root), "show", f"{revision}:{relative}"],
            check=True,
            capture_output=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise W06C0R1Error(f"scope drift anchor blob is unreadable: {relative}") from exc
    return _sha(completed.stdout.replace(b"\r\n", b"\n").replace(b"\r", b"\n"))


def _validate_pin_anchor(root: Path, scope_end_revision: str, head_revision: str) -> str:
    """Reject renewal of the one-time pin after its immutable Git anchor."""

    anchor = _git_pin_anchor_revision(root, scope_end_revision)
    _require_ancestor(root, scope_end_revision, anchor, "scope drift pin anchor")
    anchored_paths = set(_post_scope_owned_paths(_git_changed_paths(root, scope_end_revision, anchor)))
    if anchored_paths != set(SCOPE_DRIFT_MAINTENANCE_FILES):
        raise W06C0R1Error("scope drift pin anchor does not contain the exact maintenance set")
    later_paths = _post_scope_owned_paths(_git_changed_paths(root, anchor, head_revision))
    if later_paths:
        raise W06C0R1Error(
            f"protected scope paths changed after maintenance anchor: {list(later_paths)}"
        )
    for relative in SCOPE_DRIFT_MAINTENANCE_FILES:
        current_path = SCOPE_DRIFT_PIN if relative == SCOPE_DRIFT_PIN_RELATIVE else root / relative
        if _file_sha(current_path, f"scope drift maintenance path is unreadable: {relative}") != _git_blob_sha(root, anchor, relative):
            raise W06C0R1Error(f"scope drift maintenance path changed since anchor: {relative}")
    return anchor


def _load_scope_drift_pin(root: Path) -> Mapping[str, Any]:
    """Validate the one-time post-end maintenance evidence pin."""

    metadata = _load_json(SCOPE_DRIFT_PIN, "scope drift pin is unreadable")
    if (
        metadata.get("schema_version") != 1
        or metadata.get("compatibility_id") != SCOPE_DRIFT_PIN_ID
        or metadata.get("scope_end_revision") != IMPLEMENTATION_SCOPE_END_REVISION
        or metadata.get("maintenance_paths") != sorted(SCOPE_DRIFT_MAINTENANCE_FILES)
    ):
        raise W06C0R1Error("scope drift pin is not pinned")
    expected_source = metadata.get("source_fingerprint")
    expected_manifest = metadata.get("manifest_hash")
    expected_seal = metadata.get("seal_hash")
    expected_evidence = metadata.get("evidence_hashes")
    if (
        not isinstance(expected_source, str)
        or not isinstance(expected_manifest, str)
        or not isinstance(expected_seal, str)
        or not isinstance(expected_evidence, Mapping)
        or set(expected_evidence) != {"dev", "test", "holdout"}
    ):
        raise W06C0R1Error("scope drift pin fields are invalid")
    if source_fingerprint(root) != expected_source:
        raise W06C0R1Error("scope drift pin source fingerprint mismatch")
    manifest = _load_json(root / "evals" / "corpus-v4" / "manifest.json", "scope drift manifest is unreadable")
    if manifest.get("manifest_hash") != expected_manifest:
        raise W06C0R1Error("scope drift pin manifest hash mismatch")
    seal = _load_json(root / "evals" / "corpus-v4" / "holdout" / "seal.json", "scope drift seal is unreadable")
    if seal.get("seal_hash") != expected_seal:
        raise W06C0R1Error("scope drift pin seal hash mismatch")
    for split in ("dev", "test", "holdout"):
        evidence_path = root / "evals" / "w06c0r1" / "evidence" / f"{split}.json"
        if _file_sha(evidence_path, f"scope drift {split} evidence is unreadable") != expected_evidence[split]:
            raise W06C0R1Error(f"scope drift pin {split} evidence hash mismatch")
    head = _resolve_revision(root, "HEAD", "current HEAD")
    _validate_pin_anchor(root, metadata["scope_end_revision"], head)
    return metadata


def _post_scope_owned_paths(paths: Sequence[str]) -> tuple[str, ...]:
    return tuple(
        path
        for path in paths
        if path == SCOPE_DRIFT_PIN_RELATIVE or path in SCOPE_DRIFT_HISTORICAL_PIN_RELATIVE
        or any(path.startswith(prefix) for prefix in POST_SCOPE_PROTECTED_PREFIXES)
    )


def _case_files(root: Path, split: str) -> list[Path]:
    return sorted(path for path in (root / split).glob("*.json") if path.name != "seal.json")


def _split_fingerprint(root: Path, split: str) -> str:
    digest = bytearray()
    for path in _case_files(root, split):
        digest.extend(_frame(path.relative_to(root).as_posix()))
        digest.extend(_frame(_normalized_bytes(path)))
    return _sha(bytes(digest))


def _attestation_fingerprint(root: Path) -> str:
    digest = bytearray()
    for path in sorted((root / "attestations").glob("*.json")):
        digest.extend(_frame(path.relative_to(root).as_posix()))
        digest.extend(_frame(_normalized_bytes(path)))
    return _sha(bytes(digest))


def _tracked_source_files(root: Path) -> set[str]:
    try:
        completed = subprocess.run(
            ["git", "-C", str(root), "ls-files"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise W06C0R1Error("cannot inspect tracked evaluator files") from exc
    return {
        line.replace("\\", "/")
        for line in completed.stdout.splitlines()
        if line.replace("\\", "/").endswith(".py")
        and any(line.replace("\\", "/").startswith(prefix) for prefix in EVAL_SOURCE_PREFIXES)
    }


def source_fingerprint(root: Path | str = ROOT) -> str:
    root = Path(root).resolve()
    tracked = _tracked_source_files(root)
    filesystem = {
        path.relative_to(root).as_posix()
        for prefix in EVAL_SOURCE_PREFIXES
        for path in (root / prefix.rstrip("/")).parent.rglob("*.py")
        if path.is_file() and path.relative_to(root).as_posix().startswith(prefix)
    }
    if tracked != filesystem or not tracked:
        raise W06C0R1Error(
            f"source allowlist mismatch: tracked={sorted(tracked)}, filesystem={sorted(filesystem)}"
        )
    digest = bytearray()
    for relative in sorted(tracked):
        path = root / relative
        if path.is_symlink() or not path.is_file():
            raise W06C0R1Error(f"source file is missing or symlinked: {relative}")
        digest.extend(_frame(relative))
        digest.extend(_frame(_normalized_bytes(path)))
    return _sha(bytes(digest))


def _historical_scope_compatibility(root: Path, changed: Sequence[str]) -> dict[str, Any] | None:
    path = HISTORICAL_SCOPE_COMPAT_METADATA
    if not path.is_file() or path.is_symlink():
        return None
    metadata = _load_json(path, "historical scope compatibility metadata is unreadable")
    if metadata.get("schema_version") != 1 or metadata.get("compatibility_id") != HISTORICAL_SCOPE_COMPAT_ID:
        raise W06C0R1Error("historical scope compatibility metadata is invalid")
    compat_path = metadata.get("path")
    scope_end = metadata.get("scope_end_revision")
    expected = metadata.get("expected_blob_sha256")
    if (
        compat_path != "evals/w06c0/evaluation.py"
        or scope_end != HISTORICAL_SCOPE_COMPAT_SCOPE_END_REVISION
        or expected != HISTORICAL_SCOPE_COMPAT_BLOB_SHA256
    ):
        raise W06C0R1Error("historical scope compatibility metadata is not pinned")
    if compat_path not in changed:
        raise W06C0R1Error("historical scope compatibility path is missing from scope diff")
    target = root / compat_path
    if not target.is_file() or target.is_symlink() or _sha(_normalized_bytes(target)) != HISTORICAL_SCOPE_COMPAT_BLOB_SHA256:
        raise W06C0R1Error("historical scope compatibility blob hash mismatch")
    try:
        head = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip()
        resolved_end = subprocess.run(["git", "-C", str(root), "rev-parse", "--verify", f"{scope_end}^{{commit}}"], check=True, capture_output=True, text=True).stdout.strip()
        chronology = subprocess.run(["git", "-C", str(root), "merge-base", "--is-ancestor", resolved_end, head], check=False, capture_output=True)
    except (OSError, subprocess.CalledProcessError) as exc:
        raise W06C0R1Error("cannot verify historical scope compatibility revision") from exc
    if chronology.returncode != 0:
        raise W06C0R1Error("historical scope compatibility revision is not an ancestor")
    return {"path": compat_path, "scope_end_revision": resolved_end, "expected_blob_sha256": expected}


def verify_scope_diff(
    *,
    base_revision: str = IMPLEMENTATION_BASE_REVISION,
    scope_end_revision: str = IMPLEMENTATION_SCOPE_END_REVISION,
    root: Path | str = ROOT,
) -> dict[str, Any]:
    """Verify the frozen W-06C0R1 range and bounded post-end maintenance pin."""

    root = Path(root).resolve()
    if not re.fullmatch(r"[0-9a-f]{7,40}", base_revision):
        raise W06C0R1Error("scope base revision is invalid")
    if not re.fullmatch(r"[0-9a-f]{40}", scope_end_revision):
        raise W06C0R1Error("scope end revision is invalid")
    resolved_base = _resolve_revision(root, base_revision, "scope base")
    resolved_end = _resolve_revision(root, scope_end_revision, "scope end")
    head = _resolve_revision(root, "HEAD", "current HEAD")
    _require_ancestor(root, resolved_base, resolved_end, "scope end")
    _require_ancestor(root, resolved_end, head, "current HEAD")

    historical_changed = _git_changed_paths(root, resolved_base, resolved_end)
    worktree_changed = _git_changed_paths(root, "HEAD")
    post_end_changed = _git_changed_paths(root, resolved_end, head)
    compatibility = _historical_scope_compatibility(root, historical_changed)

    invalid_historical = tuple(
        path
        for path in historical_changed
        if path not in ALLOWED_SCOPE_FILES
        and not any(path.startswith(prefix) for prefix in ALLOWED_SCOPE_PREFIXES)
        and not (compatibility and path == compatibility["path"])
    )
    invalid_worktree = tuple(
        path
        for path in worktree_changed
        if path not in ALLOWED_SCOPE_FILES
        and path not in SCOPE_DRIFT_DOCUMENTATION_FILES
        and path not in SCOPE_DRIFT_MAINTENANCE_FILES
        and not any(path.startswith(prefix) for prefix in ALLOWED_SCOPE_PREFIXES)
        and not (compatibility and path == compatibility["path"])
    )
    if invalid_historical or invalid_worktree:
        invalid = tuple(sorted(set(invalid_historical + invalid_worktree)))
        raise W06C0R1Error(f"scope allowlist violation: {list(invalid)}")

    post_scope_owned = _post_scope_owned_paths(post_end_changed)
    if post_scope_owned:
        pin = _load_scope_drift_pin(root)
        unpinned = tuple(path for path in post_scope_owned if path not in SCOPE_DRIFT_MAINTENANCE_FILES)
        if unpinned:
            raise W06C0R1Error(f"post-scope package paths changed after pinned end: {list(unpinned)}")
    else:
        pin = None

    forbidden = tuple(
        path
        for path in sorted(set(invalid_historical + invalid_worktree))
        if any(path.startswith(prefix) for prefix in FORBIDDEN_SCOPE_PREFIXES)
    )
    return {
        "base_revision": base_revision,
        "scope_end_revision": resolved_end,
        "head_revision": head,
        "historical_changed_paths": list(historical_changed),
        "post_end_changed_paths": list(post_end_changed),
        "worktree_changed_paths": list(worktree_changed),
        "changed_paths": list(sorted(set(historical_changed + worktree_changed))),
        "forbidden_paths": list(forbidden),
        "historical_scope_compatibility": compatibility,
        "scope_drift_pin": dict(pin) if pin is not None else None,
        "status": "PASS",
    }


def _validate_label(value: Mapping[str, Any], location: str) -> None:
    status = value.get("status")
    reason = value.get("reason")
    if status not in ANSWERABILITY_STATUSES or reason not in ANSWERABILITY_REASONS:
        raise W06C0R1Error(f"{location} has unknown answerability status/reason")
    if value.get("review_version") != EVALUATOR_VERSION:
        raise W06C0R1Error(f"{location} review version is invalid")


def _verify_attestation(case: Mapping[str, Any], attestation: Mapping[str, Any], split: str) -> None:
    answerability = case.get("answerability")
    if not isinstance(answerability, Mapping):
        raise W06C0R1Error("case answerability is missing")
    _validate_label(answerability, f"{case.get('task_id')}.answerability")
    case_hash = _case_payload_hash(case)
    if answerability.get("case_payload_hash") != case_hash:
        raise W06C0R1Error(f"case payload hash mismatch: {case.get('task_id')}")
    required = {"schema_version", "corpus_version", "case_id", "split", "review_version", "case_payload_hash", "labelers", "agreement", "attestation_hash"}
    if set(attestation) != required:
        raise W06C0R1Error(f"attestation shape mismatch: {case.get('task_id')}")
    if attestation.get("schema_version") != 1 or attestation.get("corpus_version") != CORPUS_VERSION:
        raise W06C0R1Error("attestation version mismatch")
    if attestation.get("case_id") != case.get("task_id") or attestation.get("split") != split:
        raise W06C0R1Error("attestation case/split mismatch")
    if attestation.get("review_version") != EVALUATOR_VERSION or attestation.get("case_payload_hash") != case_hash:
        raise W06C0R1Error("attestation payload binding mismatch")
    labelers = attestation.get("labelers")
    if not isinstance(labelers, list) or len(labelers) != 2:
        raise W06C0R1Error("attestation must contain exactly two labelers")
    if any(not isinstance(labeler, Mapping) for labeler in labelers):
        raise W06C0R1Error("attestation labeler shape is invalid")
    if labelers[0].get("id_hash") == labelers[1].get("id_hash"):
        raise W06C0R1Error("attestation labelers must be distinct")
    for labeler in labelers:
        if set(labeler) != {"id_hash", "status", "reason"} or not re.fullmatch(r"sha256:[0-9a-f]{64}", str(labeler.get("id_hash"))):
            raise W06C0R1Error("attestation labeler identity is invalid")
        _validate_label({"status": labeler.get("status"), "reason": labeler.get("reason"), "review_version": EVALUATOR_VERSION}, "attestation label")
    agreement = labelers[0]["status"] == labelers[1]["status"] and labelers[0]["reason"] == labelers[1]["reason"]
    if attestation.get("agreement") is not agreement:
        raise W06C0R1Error("attestation agreement bit is invalid")
    if not agreement and answerability.get("status") != "review_required":
        raise W06C0R1Error("disagreement must be review_required")
    if agreement and (answerability.get("status") != labelers[0]["status"] or answerability.get("reason") != labelers[0]["reason"]):
        raise W06C0R1Error("case label does not match attestation")
    if answerability.get("attestation_hash") != attestation.get("attestation_hash") or _attestation_hash(attestation) != attestation.get("attestation_hash"):
        raise W06C0R1Error("attestation hash mismatch")


def verify_seal(root: Path | str = CORPUS_ROOT) -> Mapping[str, Any]:
    root = Path(root)
    seal = _load_json(root / "holdout" / "seal.json", "holdout seal is unreadable")
    if seal.get("state") != "SEALED" or seal.get("corpus_version") != CORPUS_VERSION:
        raise W06C0R1Error("holdout is not sealed")
    for field in ("sealed_at_revision", "dev_test_evidence_revision"):
        if not isinstance(seal.get(field), str) or not re.fullmatch(r"[0-9a-f]{40}", seal[field]):
            raise W06C0R1Error(f"holdout seal {field} is invalid")
    report_hashes = seal.get("dev_test_report_hashes")
    if not isinstance(report_hashes, list) or len(report_hashes) != 2 or any(
        not isinstance(value, str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", value)
        for value in report_hashes
    ):
        raise W06C0R1Error("holdout seal has no frozen DEV/TEST evidence")
    report_paths = (root.parents[1] / "evals" / "w06c0r1" / "evidence" / "dev.json",
                    root.parents[1] / "evals" / "w06c0r1" / "evidence" / "test.json")
    if any(not path.is_file() or path.is_symlink() for path in report_paths):
        raise W06C0R1Error("frozen DEV/TEST evidence artifacts are missing")
    if [
        _sha(_normalized_bytes(path)) for path in report_paths
    ] != report_hashes:
        raise W06C0R1Error("frozen DEV/TEST evidence hash mismatch")
    if seal.get("seal_hash") != _sha(_canonical({key: value for key, value in seal.items() if key != "seal_hash"})):
        raise W06C0R1Error("holdout seal hash mismatch")
    manifest = _load_json(root / "manifest.json", "manifest is unreadable")
    if seal.get("manifest_hash") != manifest.get("manifest_hash"):
        raise W06C0R1Error("holdout seal manifest mismatch")
    if seal.get("split_fingerprint") != manifest.get("split_fingerprints", {}).get("holdout"):
        raise W06C0R1Error("holdout seal split mismatch")
    if seal.get("attestation_fingerprint") != manifest.get("attestation_fingerprint"):
        raise W06C0R1Error("holdout seal attestation mismatch")
    try:
        repository = root.parents[1]
        chronology = subprocess.run(
            ["git", "-C", str(repository), "merge-base", "--is-ancestor", seal["dev_test_evidence_revision"], seal["sealed_at_revision"]],
            check=False,
            capture_output=True,
        )
    except OSError as exc:
        raise W06C0R1Error("cannot verify holdout seal chronology") from exc
    if chronology.returncode != 0:
        raise W06C0R1Error("DEV/TEST evidence is not an ancestor of the holdout seal")
    return seal


def verify_manifest(root: Path | str = CORPUS_ROOT, *, read_splits: Sequence[str] = SPLITS) -> dict[str, Any]:
    root = Path(root).resolve()
    manifest = _load_json(root / "manifest.json", "manifest is unreadable")
    required = {"schema_version", "corpus_version", "suite_counts", "minimum_answerable_counts", "split_statistics", "answerability_version", "provenance_version", "split_directories", "attestation_directory", "files", "split_fingerprints", "attestation_fingerprint", "phenomena_counts", "phenomena_by_case", "source_fingerprint", "manifest_hash"}
    if set(manifest) != required:
        raise W06C0R1Error("manifest shape mismatch")
    if manifest["schema_version"] != 1 or manifest["corpus_version"] != CORPUS_VERSION or manifest["answerability_version"] != EVALUATOR_VERSION or manifest["provenance_version"] != PROVENANCE_VERSION:
        raise W06C0R1Error("manifest version mismatch")
    if manifest["suite_counts"] != SUITE_COUNTS or manifest["minimum_answerable_counts"] != MINIMUM_ANSWERABLE or manifest["split_directories"] != list(SPLITS):
        raise W06C0R1Error("manifest split/count contract mismatch")
    if manifest["manifest_hash"] != _manifest_hash(manifest):
        raise W06C0R1Error("manifest hash mismatch")
    read = tuple(read_splits)
    if any(split not in SPLITS for split in read):
        raise W06C0R1Error("unknown manifest split")
    files = manifest["files"]
    for split in read:
        paths = _case_files(root, split)
        if len(paths) != SUITE_COUNTS[split]:
            raise W06C0R1Error(f"{split} case count mismatch")
        answerable = 0
        status_counts = Counter()
        actual_phenomena = Counter()
        for path in paths:
            rel = path.relative_to(root).as_posix()
            if rel not in files or path.is_symlink():
                raise W06C0R1Error(f"case manifest entry missing: {rel}")
            data = _normalized_bytes(path)
            entry = files[rel]
            if entry.get("sha256") != _sha(data) or entry.get("bytes") != len(data):
                raise W06C0R1Error(f"case fingerprint mismatch: {rel}")
            case = _load_json(path, f"case is unreadable: {rel}")
            attestation_path = root / "attestations" / path.name
            attestation = _load_json(attestation_path, f"attestation is unreadable: {path.name}")
            _verify_attestation(case, attestation, split)
            status = case["answerability"]["status"]
            status_counts[status] += 1
            if status == "answerable":
                answerable += 1
            actual_phenomena.update(manifest["phenomena_by_case"][split].get(case["task_id"], []))
        if answerable < MINIMUM_ANSWERABLE[split]:
            raise W06C0R1Error(f"{split} answerable minimum is not met")
        expected_statistics = manifest["split_statistics"].get(split)
        actual_statistics = {
            "case_count": len(paths),
            "answerable_count": status_counts.get("answerable", 0),
            "unanswerable_count": status_counts.get("unanswerable", 0),
            "review_required_count": status_counts.get("review_required", 0),
        }
        if expected_statistics != actual_statistics:
            raise W06C0R1Error(f"{split} answerability statistics mismatch")
        expected_phenomena = manifest["phenomena_counts"][split]
        if any(actual_phenomena.get(name, 0) < 1 for name in PHENOMENA) or any(expected_phenomena.get(name, 0) != actual_phenomena.get(name, 0) for name in PHENOMENA):
            raise W06C0R1Error(f"{split} phenomenon coverage mismatch")
        if manifest["split_fingerprints"].get(split) != _split_fingerprint(root, split):
            raise W06C0R1Error(f"{split} split fingerprint mismatch")
    if set(files) != {
        *(f"{split}/{path.name}" for split in SPLITS for path in _case_files(root, split)),
        *(f"attestations/{path.name}" for path in sorted((root / "attestations").glob("*.json"))),
    }:
        raise W06C0R1Error("manifest file set mismatch")
    if set(read) == set(SPLITS) and manifest["attestation_fingerprint"] != _attestation_fingerprint(root):
        raise W06C0R1Error("attestation fingerprint mismatch")
    repository = root.parents[1]
    if manifest["source_fingerprint"] != source_fingerprint(repository):
        raise W06C0R1Error("manifest source fingerprint mismatch")
    return dict(manifest)


def load_corpus(split: str, root: Path | str = CORPUS_ROOT, *, allow_holdout: bool = False) -> tuple[list[Mapping[str, Any]], tuple[GoldenTask, ...], dict[str, Any]]:
    if split not in SPLITS:
        raise W06C0R1Error(f"unsupported split: {split}")
    if split == "holdout" and not allow_holdout:
        raise W06C0R1Error("holdout requires explicit final-probe unlock")
    root = Path(root).resolve()
    manifest = verify_manifest(root, read_splits=(split,))
    fixture = load_fixture(FIXTURE_PATH)
    documents: list[Mapping[str, Any]] = []
    tasks: list[GoldenTask] = []
    for path in _case_files(root, split):
        document = _load_json(path, f"case is unreadable: {path.name}")
        documents.append(document)
        tasks.append(parse_task({key: value for key, value in document.items() if key != "answerability"}, fixture, str(path)))
    return documents, tuple(tasks), manifest


def task_set_fingerprint(split: str, case_ids: Sequence[str]) -> str:
    payload = bytearray()
    payload.extend(_frame(split))
    payload.extend(len(case_ids).to_bytes(8, "big"))
    for case_id in case_ids:
        payload.extend(_frame(case_id))
    return _sha(bytes(payload))


def candidate_content_fingerprint(rows: Iterable[Mapping[str, Any]]) -> str:
    frames = bytearray()
    normalized_rows = []
    for row in rows:
        normalized_rows.append({
            key: row.get(key)
            for key in ("candidate_id", "type", "status", "scope", "project_id", "content")
        })
    for row in sorted(normalized_rows, key=lambda value: str(value["candidate_id"])):
        frames.extend(_frame(_canonical(row)))
    return _sha(bytes(frames))


def candidate_order_fingerprint(source_memory_revision: int, candidate_ids: Sequence[str]) -> str:
    frames = bytearray()
    frames.extend(int(source_memory_revision).to_bytes(8, "big"))
    frames.extend(len(candidate_ids).to_bytes(8, "big"))
    for candidate_id in candidate_ids:
        frames.extend(_frame(candidate_id))
    return _sha(bytes(frames))


def _snapshot(vault: Path) -> tuple[int, list[str], dict[str, dict[str, Any]], str, str]:
    document = _load_json(vault / ".claude" / "validated-memory.json", "generated snapshot is unreadable")
    revision = document.get("revision")
    records = document.get("validated_memory")
    if isinstance(revision, bool) or not isinstance(revision, int) or revision < 0 or not isinstance(records, list):
        raise W06C0R1Error("generated candidate snapshot is invalid")
    ordered: list[str] = []
    metadata: dict[str, dict[str, Any]] = {}
    rows: list[dict[str, Any]] = []
    for record in records:
        if not isinstance(record, Mapping) or not isinstance(record.get("memory_id"), str) or record["memory_id"] in metadata:
            raise W06C0R1Error("generated snapshot contains invalid IDs")
        memory_id = record["memory_id"]
        ordered.append(memory_id)
        metadata[memory_id] = {
            "type": record.get("type"), "status": record.get("status"), "scope": record.get("scope"),
            "project_id": record.get("project_id") or None, "content": record.get("content", ""),
        }
        rows.append({"candidate_id": memory_id, **{key: metadata[memory_id].get(key) for key in ("type", "status", "scope", "project_id", "content")}})
    return revision, ordered, metadata, candidate_content_fingerprint(rows), candidate_order_fingerprint(revision, ordered)


def _provider(slot: str) -> tuple[Any, str]:
    if slot == "v1":
        return BaselineContextProvider(), "context_compiler_baseline_v1"
    if slot == "w06b":
        return TaskAwareV1ContextProvider(), "context_compiler_w06b_task_aware_v1"
    if slot == "v2":
        return CompilerV2ContextProvider(), "context_compiler_v2"
    if slot == "authority_lexical":
        return AuthorityContextProvider(), "metadata_authority_v1"
    raise W06C0R1Error(f"unknown core provider: {slot}")


def _select_ids(result: NormalizedEvaluationResult, candidate_ids: Sequence[str]) -> list[str]:
    values = [item.id for item in result.selected_items]
    if len(values) != len(set(values)):
        raise W06C0R1Error("provider returned duplicate candidate IDs")
    if not set(values).issubset(set(candidate_ids)):
        raise W06C0R1Error("provider returned unknown candidate ID")
    return values


def _safety(task: GoldenTask, selected: Sequence[str], metadata: Mapping[str, Mapping[str, Any]]) -> dict[str, int]:
    counts = Counter({name: 0 for name in ("wrong_project_leakage", "forbidden_leakage", "superseded_leakage", "resolved_leakage", "secret_leakage")})
    for memory_id in selected:
        record = metadata.get(memory_id)
        if record is None:
            counts["forbidden_leakage"] += 1
            continue
        if memory_id in task.forbidden:
            counts["forbidden_leakage"] += 1
        if (
            record.get("project_id") is not None
            if task.project_id is None
            else record.get("project_id") not in {None, task.project_id}
        ):
            counts["wrong_project_leakage"] += 1
        status = str(record.get("status", "")).lower()
        if status == "superseded" and not task.inactive_allowed:
            counts["superseded_leakage"] += 1
        if status == "resolved" and not task.inactive_allowed:
            counts["resolved_leakage"] += 1
        if contains_secret(str(record.get("content", ""))):
            counts["secret_leakage"] += 1
    return dict(counts)


def _metric_rows(selected: Sequence[str], document: Mapping[str, Any], metadata: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    required = set(document["expected_context"]["required"])
    useful = set(document["expected_context"]["useful"])
    relevant = required | useful
    if not required:
        raise W06C0R1Error("answerable case requires required memory")
    estimator = ConservativeTokenEstimator()
    rows: dict[str, Any] = {}
    for k in K_VALUES:
        top = list(selected[:k])
        hit = len(set(top) & relevant)
        mandatory = len(set(top) & required)
        count = len(top)
        token_counts = {item: estimator.estimate(str(metadata[item].get("content", ""))).count for item in top if item in metadata}
        total_tokens = sum(token_counts.values())
        noise_tokens = sum(token_counts[item] for item in set(top) - relevant)
        precision = hit / count if count else 0.0
        recall = hit / len(relevant) if relevant else 0.0
        mandatory_recall = mandatory / len(required)
        f1 = 0.0 if precision == 0 or recall == 0 else 2 * precision * recall / (precision + recall)
        rows[str(k)] = {
            "precision": precision, "recall": recall, "f1": f1,
            "mrr": next((1.0 / (index + 1) for index, item in enumerate(top) if item in relevant), 0.0),
            "mandatory_recall": mandatory_recall,
            "noise_ratio": (count - hit) / max(count, 1),
            "token_waste": noise_tokens / total_tokens if total_tokens else 0.0,
            "selected_count": count,
        }
    return rows


def _averages(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    names = ("precision", "recall", "f1", "mrr", "mandatory_recall", "noise_ratio", "token_waste")
    return {
        str(k): {
            name: (sum(float(row["metrics"][str(k)][name]) for row in rows) / len(rows) if rows else None)
            for name in names
        }
        for k in K_VALUES
    }


def _empty_provider(slot: str, documents: Sequence[Mapping[str, Any]], snapshot: tuple[int, str, str], task_fp: str) -> dict[str, Any]:
    revision, content_fp, order_fp = snapshot
    counts = Counter(document["answerability"]["status"] for document in documents)
    return {
        "slot": slot, "requested_provider_id": slot, "actual_provider_id": "unavailable", "model": "unavailable",
        "availability": "UNAVAILABLE", "run_status": "NOT_MEASURED", "fallback": False,
        "error_code": "OPTIONAL_PROVIDER_NOT_SELECTED", "provider_schema_version": 1,
        "case_count": len(documents), "scored_count": 0,
        "excluded_counts": {status: counts.get(status, 0) for status in sorted(ANSWERABILITY_STATUSES)},
        "quality": {"state": "NOT_MEASURED", "reason": "optional_provider_not_selected"}, "metrics": _averages([]),
        "safety": {name: 0 for name in ("wrong_project_leakage", "forbidden_leakage", "superseded_leakage", "resolved_leakage", "secret_leakage")},
        "source_memory_revision": revision, "candidate_content_fingerprint": content_fp,
        "candidate_order_fingerprint": order_fp, "task_set_fingerprint": task_fp,
        "rows": [],
    }


def _optional_selection(slot: str, provider: Any, task: GoldenTask, candidate_ids: Sequence[str], metadata: Mapping[str, Mapping[str, Any]], revision: int) -> NormalizedEvaluationResult:
    candidates = [
        memory_id
        for memory_id in candidate_ids
        if str(metadata[memory_id].get("status", "")).lower() == "active"
        and (
            metadata[memory_id].get("project_id") is None
            if task.project_id is None
            else metadata[memory_id].get("project_id") in {None, task.project_id}
        )
    ]
    texts = [str(metadata[memory_id].get("content", "")) for memory_id in candidates]
    if slot == "embedding":
        result = provider.embed([task.prompt, *texts])
        if result.status != EmbeddingStatus.EMBEDDING_AVAILABLE.value:
            raise W06C0R1Error(result.error_code or "SEMANTIC_UNAVAILABLE")
        if len(result.vectors) != len(candidates) + 1:
            raise W06C0R1Error("embedding_response_length_mismatch")
        query = result.vectors[0]
        ranked = []
        for memory_id, vector in zip(candidates, result.vectors[1:]):
            left = math.sqrt(sum(float(value) ** 2 for value in query))
            right = math.sqrt(sum(float(value) ** 2 for value in vector))
            if len(query) != len(vector) or not left or not right:
                score = 0.0
            else:
                score = sum(float(a) * float(b) for a, b in zip(query, vector)) / (left * right)
            ranked.append((memory_id, score))
        provider_id = str(result.provider_id)
    else:
        result = provider.rerank(task.prompt, texts)
        if result.status != EmbeddingStatus.EMBEDDING_AVAILABLE.value:
            raise W06C0R1Error(result.error_code or "RERANKER_UNAVAILABLE")
        if len(result.scores) != len(candidates):
            raise W06C0R1Error("reranker_response_length_mismatch")
        ranked = list(zip(candidates, (float(score) for score in result.scores)))
        provider_id = str(result.provider_id)
    ranked.sort(key=lambda item: (-item[1], item[0]))
    items = tuple(SelectedContextItem(id=memory_id, source_type="memory", project_id=metadata[memory_id].get("project_id") or None, memory_type=str(metadata[memory_id].get("type") or "memory"), status=str(metadata[memory_id].get("status") or "active"), content=str(metadata[memory_id].get("content") or "memory"), score=float(score)) for memory_id, score in ranked)
    return NormalizedEvaluationResult(task_id=task.task_id, provider_id=provider_id, selected_items=items, source_memory_revision=revision, project_id=task.project_id, retrieval_scope="default", capabilities={"scope_isolation": "supported", "semantic_ranking": "supported"})


def _run_matrix_provider(slot: str, documents: Sequence[Mapping[str, Any]], tasks: Sequence[GoldenTask], fixture: Any, task_fp: str, measure_optional: bool, reference_snapshot: tuple[int, str, str]) -> dict[str, Any]:
    optional = slot in {"embedding", "reranker"}
    if optional and not measure_optional:
        return _empty_provider(slot, documents, reference_snapshot, task_fp)
    provider, requested_id = ((create_embedding_provider(), slot) if slot == "embedding" else (create_reranker(), slot)) if optional else _provider(slot)
    rows: list[dict[str, Any]] = []
    source_values: set[tuple[Any, ...]] = set()
    safety_total = Counter()
    actual_ids: set[str] = set()
    errors: list[str] = []
    latencies: list[float] = []
    with tempfile.TemporaryDirectory(prefix=f"brain-eleven-w06c0r1-{slot}-") as directory:
        for index, (document, public_task) in enumerate(zip(documents, tasks), 1):
            vault = build_vault(fixture, Path(directory) / f"vault-{index:03d}", seed=SEED, noise_count=NOISE_COUNT)
            revision, candidate_ids, metadata, content_fp, order_fp = _snapshot(vault.root)
            source_values.add((revision, content_fp, order_fp))
            task = GoldenTask(task_id=f"task-{index:06d}", project_id=public_task.project_id, prompt=public_task.prompt, intent=public_task.intent, domains=public_task.domains, required=(), useful=(), forbidden=(), wrong_project_allowed=True, inactive_allowed=public_task.inactive_allowed, expectations={})
            started = perf_counter()
            selected: list[str] = []
            status = "COMPLETE"
            error_code = None
            try:
                result = _optional_selection(slot, provider, task, candidate_ids, metadata, revision) if optional else provider.select(task, vault.root)
                selected = _select_ids(result, candidate_ids)
                actual_ids.add(result.provider_id)
                latencies.append(round((perf_counter() - started) * 1000, 3))
            except Exception as error:
                status = "NOT_MEASURED" if optional and str(getattr(provider, "provider_id", "")).startswith("unavailable") else "ERROR"
                error_code = str(getattr(error, "error_code", "")) or type(error).__name__
                errors.append(error_code[:64])
                actual_ids.add(str(getattr(provider, "provider_id", requested_id)))
            answerability = document["answerability"]
            safety = _safety(public_task, selected, metadata)
            safety_total.update(safety)
            row = {"task_handle": task.task_id, "answerability": answerability["status"], "provider_status": status, "selected_hashes": [_sha(memory_id.encode("utf-8")) for memory_id in selected], "selected_count": len(selected), "latency_ms": round((perf_counter() - started) * 1000, 3), "safety": safety, "metrics": _metric_rows(selected, document, metadata) if answerability["status"] == "answerable" and status == "COMPLETE" else None}
            if error_code:
                row["error_code"] = error_code
            rows.append(row)
    if len(source_values) != 1:
        raise W06C0R1Error(f"provider {slot} did not receive one snapshot")
    revision, content_fp, order_fp = next(iter(source_values))
    scored = [row for row in rows if row["metrics"] is not None]
    counts = Counter(row["answerability"] for row in rows)
    unavailable = optional and rows and all(row["provider_status"] == "NOT_MEASURED" for row in rows)
    actual_id = sorted(actual_ids)[0] if len(actual_ids) == 1 else requested_id
    return {"slot": slot, "requested_provider_id": slot, "actual_provider_id": actual_id, "model": str(getattr(provider, "model", "existing_adapter")), "availability": "UNAVAILABLE" if unavailable else "AVAILABLE", "run_status": "NOT_MEASURED" if unavailable else ("ERROR" if errors else "COMPLETE"), "fallback": bool(actual_ids and actual_ids != {requested_id}), "provider_schema_version": 1, "error_code": errors[0] if errors else None, "case_count": len(rows), "scored_count": len(scored), "excluded_counts": {status: counts.get(status, 0) for status in sorted(ANSWERABILITY_STATUSES)}, "quality": {"state": "INSUFFICIENT_ANSWERABLE_CASES" if not scored else "MEASURED", "reason": "no_answerable_cases" if not scored else None}, "metrics": _averages(scored), "safety": dict(sorted(safety_total.items())), "latency_ms": {"p50": statistics.median(latencies) if latencies else None, "p95": latencies[max(0, math.ceil(len(latencies) * 0.95) - 1)] if latencies else None}, "source_memory_revision": revision, "candidate_content_fingerprint": content_fp, "candidate_order_fingerprint": order_fp, "task_set_fingerprint": task_fp, "rows": rows}


def run_matrix(*, split: str = "dev", corpus_version: int = CORPUS_VERSION, providers: Sequence[str] = PROVIDER_SLOTS, measure_optional: bool = False, allow_holdout: bool = False, unlock_token: str | None = None) -> dict[str, Any]:
    if corpus_version != CORPUS_VERSION:
        raise W06C0R1Error("explicit corpus-v4 selection is required")
    seal: Mapping[str, Any] | None = None
    if split == "holdout":
        if not allow_holdout or not unlock_token:
            raise W06C0R1Error("holdout requires one-time unlock token")
        seal = verify_seal()
    documents, tasks, manifest = load_corpus(split, allow_holdout=allow_holdout)
    if split == "holdout" and not allow_holdout:
        raise W06C0R1Error("holdout is sealed")
    unknown = set(providers) - set(PROVIDER_SLOTS)
    if unknown:
        raise W06C0R1Error(f"unknown provider slots: {sorted(unknown)}")
    task_fp = task_set_fingerprint(split, [document["task_id"] for document in documents])
    fixture = load_fixture(FIXTURE_PATH)
    with tempfile.TemporaryDirectory(prefix="brain-eleven-w06c0r1-reference-") as directory:
        reference_vault = build_vault(fixture, Path(directory) / "vault", seed=SEED, noise_count=NOISE_COUNT)
        reference = _snapshot(reference_vault.root)
        reference_snapshot = reference[0], reference[3], reference[4]
    results = {slot: _run_matrix_provider(slot, documents, tasks, fixture, task_fp, measure_optional, reference_snapshot) for slot in providers}
    safety_failures = {
        slot: {name: value for name, value in result["safety"].items() if value}
        for slot, result in results.items()
        if any(result["safety"].values())
    }
    if safety_failures:
        raise W06C0R1Error(f"safety hard gate failed: {safety_failures}")
    snapshots = {(result["source_memory_revision"], result["candidate_content_fingerprint"], result["candidate_order_fingerprint"], result["task_set_fingerprint"]) for result in results.values()}
    if len(snapshots) > 1:
        raise W06C0R1Error("provider snapshot/task fingerprints differ")
    quality = "INSUFFICIENT_ANSWERABLE_CASES" if not any(result["scored_count"] for result in results.values()) else "MEASURED"
    report = {"schema_version": 1, "evaluator_version": EVALUATOR_VERSION, "corpus_version": CORPUS_VERSION, "report_type": "brain_eleven_w06c0r1_feasibility", "corpus": {"split": split, "case_count": len(documents), "manifest_hash": manifest["manifest_hash"], "split_fingerprint": manifest["split_fingerprints"][split], "excluded_counts": {status: sum(document["answerability"]["status"] == status for document in documents) for status in sorted(ANSWERABILITY_STATUSES)}}, "source": {"source_fingerprint": source_fingerprint(), "task_set_fingerprint": task_fp, "seed": SEED, "noise_count": NOISE_COUNT, "k_values": list(K_VALUES), "holdout_included": split == "holdout"}, "quality": {"state": quality, "reason": "no answerable cases were scored" if quality != "MEASURED" else None}, "providers": results, "promotion": "blocked", "production_mutation": False}
    if seal is not None:
        report["holdout_evidence"] = {
            "seal_hash": seal["seal_hash"],
            "unlock_token_hash": _sha(str(unlock_token).encode("utf-8")),
        }
    return report


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the W-06C0R1 evaluation-only feasibility matrix")
    parser.add_argument("--corpus-version", type=int, choices=(CORPUS_VERSION,), required=True)
    parser.add_argument("--split", choices=SPLITS, default="dev")
    parser.add_argument("--providers", nargs="+", choices=PROVIDER_SLOTS, default=list(PROVIDER_SLOTS))
    parser.add_argument("--measure-optional", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--final-holdout", action="store_true")
    parser.add_argument("--unlock-token")
    args = parser.parse_args(argv)
    if args.final_holdout:
        if args.split != "holdout":
            raise W06C0R1Error("final holdout requires the holdout split")
        if args.output.resolve() != FINAL_HOLDOUT_OUTPUT.resolve():
            raise W06C0R1Error("final holdout output must use the canonical evidence path")
        if args.output.exists():
            raise W06C0R1Error("holdout output already exists; unlock token cannot be replayed")
    report = run_matrix(split=args.split, corpus_version=args.corpus_version, providers=args.providers, measure_optional=args.measure_optional, allow_holdout=args.final_holdout, unlock_token=args.unlock_token)
    if args.final_holdout:
        report["holdout_evidence"]["command_hash"] = _sha(_canonical(list(argv if argv is not None else sys.argv[1:])))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "split": args.split, "quality": report["quality"], "providers": sorted(report["providers"])}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
