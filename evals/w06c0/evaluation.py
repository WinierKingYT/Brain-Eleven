"""W-06C0 retrieval feasibility harness.

This module is deliberately evaluation-only.  It builds isolated synthetic
vaults, runs existing read-only provider adapters, and emits content-free
evidence.  No active retrieval path or canonical authority is imported for
mutation; all temporary writes are confined to a temporary vault.
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
import tempfile
from pathlib import Path
from time import perf_counter
from typing import Any, Iterable, Mapping, Sequence

from context_compiler_v2.safety import contains_secret
from context_compiler_v2.tokenizer import ConservativeTokenEstimator
from brain_eleven.retrieval import EmbeddingStatus, create_embedding_provider, create_reranker
from evals.authority_provider import AuthorityContextProvider
from evals.baseline import BaselineContextProvider, TaskAwareV1ContextProvider
from evals.compiler_v2_provider import CompilerV2ContextProvider
from evals.contracts import NormalizedEvaluationResult, SelectedContextItem
from evals.fixture_generator import build_vault
from evals.schema import GoldenTask, load_fixture, parse_task


ROOT = Path(__file__).resolve().parents[2]
CORPUS_ROOT = ROOT / "evals" / "corpus-v3"
FIXTURE_PATH = ROOT / "evals" / "fixtures" / "phase15-contract.json"
K_VALUES = (1, 3, 5, 10)
PROVIDER_SLOTS = ("v1", "w06b", "v2", "authority_lexical", "embedding", "reranker")
CORE_PROVIDERS = PROVIDER_SLOTS[:4]
SPLITS = ("dev", "test", "holdout")
SEED = 17
NOISE_COUNT = 24
MANIFEST_SCHEMA_VERSION = 1
CORPUS_VERSION = 3
ANSWERABILITY_VERSION = "w06c0-v1"
SOURCE_FILES = (
    "evals/w06c0/__init__.py",
    "evals/w06c0/__main__.py",
    "evals/w06c0/evaluation.py",
)
IMPLEMENTATION_BASE_REVISION = "fa5b920"
ALLOWED_SCOPE_PREFIXES = (
    "evals/corpus-v3/",
    "evals/w06c0/",
    "tests/test_w06c0_",
)
ALLOWED_SCOPE_FILES = frozenset({"WEAKNESS-W06C0-PACKAGE-REPORT.md"})
FORBIDDEN_SCOPE_PREFIXES = (
    "brain_eleven/",
    "scripts/",
    "context_compiler_v2/",
    "authority/",
    "context_router/",
    ".claude/",
    "evals/w09a/",
    "evals/corpus-v2/",
)
REASONS = frozenset(
    {
        "query_and_candidate_metadata_support_target",
        "query_lacks_target_discriminator",
        "gold_label_depends_on_hidden_fixture_metadata",
        "candidate_snapshot_incomplete",
        "annotation_disagreement",
        "privacy_or_schema_review",
    }
)
STATUSES = frozenset({"answerable", "unanswerable", "review_required"})


class W06C0Error(ValueError):
    """Raised when the W-06C0 evidence boundary is invalid."""


def _sha256(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _normal(value: bytes) -> bytes:
    return value.replace(b"\r\n", b"\n").replace(b"\r", b"\n")


def _frame(relative: str, value: bytes) -> bytes:
    path = relative.encode("utf-8")
    return len(path).to_bytes(8, "big") + path + len(value).to_bytes(8, "big") + value


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _manifest_hash(manifest: Mapping[str, Any]) -> str:
    payload = dict(manifest)
    payload.pop("manifest_sha256", None)
    return _sha256(_canonical(payload))


def _repo_tracked_files() -> set[str]:
    try:
        completed = subprocess.run(
            ["git", "-C", str(ROOT), "ls-files", "--", "evals/w06c0"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as error:
        raise W06C0Error("cannot verify W-06C0 tracked source allowlist") from error
    return {line.replace("\\", "/") for line in completed.stdout.splitlines() if line.strip()}


def source_fingerprint(root: Path | str = ROOT) -> str:
    """Hash the exact, versioned W-06C0 source allowlist.

    The explicit file list prevents a newly added evaluator/provider from
    silently changing the evidence identity.  Tests may call this only after
    the bounded source commit exists; untracked allowlist files fail closed.
    """

    root = Path(root)
    expected = set(SOURCE_FILES)
    tracked = _repo_tracked_files()
    if tracked != expected:
        raise W06C0Error(f"source allowlist mismatch: expected {sorted(expected)}, got {sorted(tracked)}")
    digest = hashlib.sha256()
    for relative in SOURCE_FILES:
        path = root / relative
        if not path.is_file() or path.is_symlink():
            raise W06C0Error(f"source allowlist file missing or symlinked: {relative}")
        digest.update(_frame(relative, _normal(path.read_bytes())))
    return "sha256:" + digest.hexdigest()


def verify_scope_diff(
    *,
    base_revision: str = IMPLEMENTATION_BASE_REVISION,
    root: Path | str = ROOT,
) -> dict[str, Any]:
    """Fail closed when the W-06C0 tree leaves its bounded allowlist.

    The check is intentionally based on a full revision range rather than the
    current working tree.  This gives the package report a reproducible
    before/after assertion and catches a forbidden tracked-path change before
    a feasibility report can be accepted.
    """

    root = Path(root)
    if not re.fullmatch(r"[0-9a-f]{7,40}", base_revision):
        raise W06C0Error("W-06C0 scope base revision is invalid")
    try:
        completed = subprocess.run(
            [
                "git",
                "-C",
                str(root),
                "diff",
                "--name-only",
                "--diff-filter=ACDMRTUXB",
                base_revision,
                "--",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        current = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError) as error:
        raise W06C0Error("cannot verify W-06C0 scope diff") from error
    changed = tuple(sorted({line.replace("\\", "/") for line in completed.stdout.splitlines() if line.strip()}))
    invalid = tuple(
        path
        for path in changed
        if path not in ALLOWED_SCOPE_FILES
        and not any(path.startswith(prefix) for prefix in ALLOWED_SCOPE_PREFIXES)
    )
    forbidden = tuple(path for path in invalid if any(path.startswith(prefix) for prefix in FORBIDDEN_SCOPE_PREFIXES))
    if invalid:
        raise W06C0Error(f"W-06C0 scope allowlist violation: {list(invalid)}")
    return {
        "base_revision": base_revision,
        "head_revision": current,
        "changed_paths": list(changed),
        "forbidden_paths": list(forbidden),
        "allowlist_status": "PASS",
    }


def verify_manifest(root: Path | str = CORPUS_ROOT) -> dict[str, Any]:
    """Verify v3 split counts, file hashes, manifest hash, and split hashes."""

    root = Path(root)
    manifest_path = root / "manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise W06C0Error("corpus-v3 manifest is unreadable") from error
    if manifest.get("schema_version") != MANIFEST_SCHEMA_VERSION or manifest.get("corpus_version") != CORPUS_VERSION:
        raise W06C0Error("unsupported corpus-v3 manifest")
    if manifest.get("split_directories") != list(SPLITS):
        raise W06C0Error("corpus-v3 split directories are not frozen")
    if manifest.get("answerability_reason_version") != ANSWERABILITY_VERSION:
        raise W06C0Error("unsupported answerability reason version")
    if manifest.get("manifest_sha256") != _manifest_hash(manifest):
        raise W06C0Error("manifest self-fingerprint mismatch")
    files = manifest.get("files")
    if not isinstance(files, Mapping):
        raise W06C0Error("manifest files must be an object")
    expected_counts = manifest.get("suite_counts")
    expected_paths: set[str] = set()
    for split in SPLITS:
        expected = expected_counts.get(split) if isinstance(expected_counts, Mapping) else None
        paths = sorted((root / split).glob("*.json"))
        if not isinstance(expected, int) or len(paths) != expected:
            raise W06C0Error(f"{split} case count mismatch")
        for path in paths:
            if path.is_symlink():
                raise W06C0Error(f"symlinked corpus case: {path}")
            relative = path.relative_to(root).as_posix()
            expected_paths.add(relative)
            data = _normal(path.read_bytes())
            entry = files.get(relative)
            if not isinstance(entry, Mapping) or entry.get("sha256") != _sha256(data) or entry.get("bytes") != len(data):
                raise W06C0Error(f"case fingerprint mismatch: {relative}")
    if set(files) != expected_paths:
        raise W06C0Error("manifest contains missing or extra case files")
    for split in SPLITS:
        digest = hashlib.sha256()
        for path in sorted((root / split).glob("*.json")):
            digest.update(_frame(path.relative_to(root).as_posix(), _normal(path.read_bytes())))
        actual = "sha256:" + digest.hexdigest()
        if manifest["split_fingerprints"].get(split) != actual:
            raise W06C0Error(f"split fingerprint mismatch: {split}")
    return manifest


def _base_document(document: Mapping[str, Any]) -> Mapping[str, Any]:
    value = dict(document)
    value.pop("answerability", None)
    return value


def _answerability(document: Mapping[str, Any]) -> Mapping[str, Any]:
    value = document.get("answerability")
    if not isinstance(value, Mapping):
        raise W06C0Error("case answerability is missing")
    if value.get("status") not in STATUSES or value.get("reason") not in REASONS:
        raise W06C0Error("case answerability status/reason is invalid")
    if value.get("review_version") != ANSWERABILITY_VERSION:
        raise W06C0Error("case answerability version is invalid")
    reviewers = value.get("reviewers")
    if (
        not isinstance(reviewers, list)
        or len(reviewers) != 2
        or len(set(reviewers)) != 2
        or any(not isinstance(item, str) or not item.strip() for item in reviewers)
    ):
        raise W06C0Error("case must have two independent labeler identities")
    provenance = value.get("provenance_hash")
    if not isinstance(provenance, str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", provenance):
        raise W06C0Error("case answerability provenance is invalid")
    return value


def load_corpus(split: str, root: Path | str = CORPUS_ROOT) -> tuple[list[Mapping[str, Any]], tuple[GoldenTask, ...], dict[str, Any]]:
    """Load a v3 split and parse its legacy task shape without changing v2."""

    if split not in SPLITS:
        raise W06C0Error(f"unsupported split: {split}")
    manifest = verify_manifest(root)
    fixture = load_fixture(FIXTURE_PATH)
    root = Path(root)
    documents: list[Mapping[str, Any]] = []
    tasks: list[GoldenTask] = []
    for path in sorted((root / split).glob("*.json")):
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise W06C0Error(f"invalid v3 case: {path.name}") from error
        _answerability(document)
        documents.append(document)
        try:
            tasks.append(parse_task(_base_document(document), fixture, str(path)))
        except Exception as error:
            raise W06C0Error(f"v3 case does not satisfy the legacy task schema: {path.name}") from error
    return documents, tuple(tasks), manifest


def _snapshot(vault: Path) -> tuple[int, list[str], dict[str, dict[str, Any]], str, str]:
    path = vault / ".claude" / "validated-memory.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    revision = document.get("revision")
    records = document.get("validated_memory")
    if isinstance(revision, bool) or not isinstance(revision, int) or revision < 0 or not isinstance(records, list):
        raise W06C0Error("generated candidate snapshot is invalid")
    ordered: list[str] = []
    metadata: dict[str, dict[str, Any]] = {}
    content_rows: list[dict[str, Any]] = []
    for record in records:
        if not isinstance(record, Mapping) or not record.get("memory_id"):
            raise W06C0Error("candidate record is invalid")
        memory_id = str(record["memory_id"])
        ordered.append(memory_id)
        project_id = record.get("project_id") or None
        metadata[memory_id] = {
            "project_id": project_id,
            "status": record.get("status"),
            "type": record.get("type"),
            "scope": record.get("scope"),
            "content": record.get("content", ""),
        }
        content_rows.append({
            "memory_id": memory_id,
            "type": record.get("type"),
            "status": record.get("status"),
            "scope": record.get("scope"),
            "project_id": project_id,
            "content": record.get("content", ""),
        })
    content = _canonical(sorted(content_rows, key=lambda row: row["memory_id"]))
    order = _canonical({"revision": revision, "ids": ordered})
    return revision, ordered, metadata, _sha256(content), _sha256(order)


def _provider(provider_id: str) -> tuple[Any, str]:
    if provider_id == "v1":
        return BaselineContextProvider(), "context_compiler_baseline_v1"
    if provider_id == "w06b":
        return TaskAwareV1ContextProvider(), "context_compiler_w06b_task_aware_v1"
    if provider_id == "v2":
        return CompilerV2ContextProvider(), "context_compiler_v2"
    if provider_id == "authority_lexical":
        return AuthorityContextProvider(), "metadata_authority_v1"
    raise W06C0Error(f"unknown core provider: {provider_id}")


def _select_ids(result: NormalizedEvaluationResult, candidate_ids: Sequence[str]) -> list[str]:
    values = [item.id for item in result.selected_items]
    if len(values) != len(set(values)):
        raise W06C0Error("provider returned duplicate candidate IDs")
    if not set(values).issubset(set(candidate_ids)):
        raise W06C0Error("provider returned an unknown candidate ID")
    return values


def _safety(task: GoldenTask, selected: Sequence[str], metadata: Mapping[str, Mapping[str, Any]]) -> dict[str, int]:
    counts = Counter({
        "wrong_project_leakage": 0,
        "forbidden_leakage": 0,
        "superseded_leakage": 0,
        "resolved_leakage": 0,
        "secret_leakage": 0,
    })
    forbidden = set(task.forbidden)
    for memory_id in selected:
        record = metadata.get(memory_id)
        if record is None:
            counts["forbidden_leakage"] += 1
            continue
        if memory_id in forbidden:
            counts["forbidden_leakage"] += 1
        if task.project_id is not None and record.get("project_id") not in {None, task.project_id}:
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
        raise W06C0Error("answerable case must declare at least one required ID")
    rows: dict[str, Any] = {}
    for k in K_VALUES:
        top = list(selected[:k])
        hit = len(set(top) & relevant)
        mandatory = len(set(top) & required)
        count = len(top)
        precision = hit / count if count else 0.0
        recall = hit / len(relevant) if relevant else 0.0
        mandatory_recall = mandatory / len(required)
        f1 = 0.0 if recall == 0.0 or precision == 0 else 2 * precision * recall / (precision + recall)
        token_counts = {
            item: ConservativeTokenEstimator().estimate(str(metadata[item].get("content", ""))).count
            for item in top
            if item in metadata
        }
        total_tokens = sum(token_counts.values())
        noise_tokens = sum(token_counts[item] for item in set(top) - relevant)
        rows[str(k)] = {
            "precision": precision,
            "recall": recall,
            "f1": f1,
            "mrr": next((1.0 / (index + 1) for index, item in enumerate(top) if item in relevant), 0.0),
            "mandatory_recall": mandatory_recall,
            "noise_ratio": (count - hit) / max(count, 1),
            "token_waste": noise_tokens / total_tokens if total_tokens else 0.0,
            "selected_count": count,
        }
    return rows


def _empty_optional(
    slot: str,
    documents: Sequence[Mapping[str, Any]],
    snapshot: tuple[int, str, str],
) -> dict[str, Any]:
    revision, content_fp, order_fp = snapshot
    answer_counts = Counter(_answerability(document)["status"] for document in documents)
    rows = [
        {
            "task_id": document["task_id"],
            "answerability": _answerability(document)["status"],
            "provider_status": "NOT_MEASURED",
            "selected_ids": [],
            "selected_count": 0,
            "latency_ms": None,
            "safety": {
                "wrong_project_leakage": 0,
                "forbidden_leakage": 0,
                "superseded_leakage": 0,
                "resolved_leakage": 0,
                "secret_leakage": 0,
            },
            "metrics": None,
        }
        for document in documents
    ]
    return {
        "slot": slot,
        "requested_provider_id": slot,
        "actual_provider_id": "unavailable",
        "model": "unavailable",
        "availability": "UNAVAILABLE",
        "run_status": "NOT_MEASURED",
        "fallback": False,
        "error_code": "OPTIONAL_PROVIDER_NOT_SELECTED",
        "case_count": len(documents),
        "scored_count": 0,
        "excluded_counts": {name: answer_counts.get(name, 0) for name in sorted(STATUSES)},
        "metrics": {},
        "quality_state": "NOT_MEASURED",
        "safety": {
            "wrong_project_leakage": 0,
            "forbidden_leakage": 0,
            "superseded_leakage": 0,
            "resolved_leakage": 0,
            "secret_leakage": 0,
        },
        "source_memory_revision": revision,
        "candidate_content_fingerprint": content_fp,
        "candidate_order_fingerprint": order_fp,
        "rows": rows,
    }


def _optional_candidates(
    task: GoldenTask,
    candidate_ids: Sequence[str],
    metadata: Mapping[str, Mapping[str, Any]],
) -> list[str]:
    """Return the fixed, scope-filtered candidate set for optional providers."""

    candidates: list[str] = []
    for memory_id in candidate_ids:
        record = metadata[memory_id]
        if str(record.get("status", "")).lower() != "active":
            continue
        project_id = record.get("project_id") or None
        if task.project_id is None:
            if project_id is not None:
                continue
        elif project_id not in {None, task.project_id}:
            continue
        candidates.append(memory_id)
    return candidates


def _optional_result(
    task: GoldenTask,
    provider_id: str,
    revision: int,
    ranked: Sequence[tuple[str, float]],
    metadata: Mapping[str, Mapping[str, Any]],
) -> NormalizedEvaluationResult:
    items = tuple(
        SelectedContextItem(
            id=memory_id,
            source_type="memory",
            project_id=metadata[memory_id].get("project_id") or None,
            memory_type=str(metadata[memory_id].get("type") or "memory"),
            status=str(metadata[memory_id].get("status") or "active"),
            content=str(metadata[memory_id].get("content") or ""),
            score=float(score),
        )
        for memory_id, score in ranked
    )
    return NormalizedEvaluationResult(
        task_id=task.task_id,
        provider_id=provider_id,
        selected_items=items,
        source_memory_revision=revision,
        project_id=task.project_id,
        retrieval_scope="default",
        capabilities={
            "scope_isolation": "supported",
            "lifecycle_filtering": "supported",
            "semantic_ranking": "supported",
        },
    )


def _optional_selection(
    slot: str,
    provider: Any,
    task: GoldenTask,
    candidate_ids: Sequence[str],
    metadata: Mapping[str, Mapping[str, Any]],
    revision: int,
) -> NormalizedEvaluationResult:
    candidates = _optional_candidates(task, candidate_ids, metadata)
    texts = [str(metadata[memory_id].get("content") or "") for memory_id in candidates]
    if slot == "embedding":
        embedded = provider.embed([task.prompt, *texts])
        if embedded.status != EmbeddingStatus.EMBEDDING_AVAILABLE.value:
            raise W06C0Error(embedded.error_code or "SEMANTIC_UNAVAILABLE")
        if len(embedded.vectors) != len(candidates) + 1:
            raise W06C0Error("embedding_response_length_mismatch")
        query = embedded.vectors[0]
        ranked = []
        for memory_id, vector in zip(candidates, embedded.vectors[1:]):
            if len(query) != len(vector) or not query:
                raise W06C0Error("embedding_dimensions_mismatch")
            numerator = sum(float(left) * float(right) for left, right in zip(query, vector))
            query_norm = math.sqrt(sum(float(value) ** 2 for value in query))
            value_norm = math.sqrt(sum(float(value) ** 2 for value in vector))
            score = numerator / (query_norm * value_norm) if query_norm and value_norm else 0.0
            ranked.append((memory_id, score))
        ranked.sort(key=lambda item: (-item[1], item[0]))
        provider_id = str(embedded.provider_id)
    elif slot == "reranker":
        reranked = provider.rerank(task.prompt, texts)
        if reranked.status != EmbeddingStatus.EMBEDDING_AVAILABLE.value:
            raise W06C0Error(reranked.error_code or "RERANKER_UNAVAILABLE")
        if len(reranked.scores) != len(candidates):
            raise W06C0Error("reranker_response_length_mismatch")
        ranked = list(zip(candidates, (float(score) for score in reranked.scores)))
        ranked.sort(key=lambda item: (-item[1], item[0]))
        provider_id = str(reranked.provider_id)
    else:
        raise W06C0Error(f"unsupported optional provider: {slot}")
    return _optional_result(task, provider_id, revision, ranked, metadata)


def _run_optional_provider(
    slot: str,
    documents: Sequence[Mapping[str, Any]],
    tasks: Sequence[GoldenTask],
    fixture: Any,
) -> dict[str, Any]:
    provider = create_embedding_provider() if slot == "embedding" else create_reranker()
    requested_id = slot
    model = str(getattr(provider, "model", "unavailable"))
    rows: list[dict[str, Any]] = []
    source_values: set[tuple[Any, ...]] = set()
    safety_total = Counter()
    actual_ids: set[str] = set()
    error_codes: list[str] = []
    measured_latencies: list[float] = []
    with tempfile.TemporaryDirectory(prefix=f"brain-eleven-w06c0-{slot}-") as directory:
        for document, task in zip(documents, tasks):
            vault = Path(directory) / task.task_id
            build_vault(fixture, vault, seed=SEED, noise_count=NOISE_COUNT)
            revision, candidate_ids, metadata, content_fp, order_fp = _snapshot(vault)
            source_values.add((revision, content_fp, order_fp))
            started = perf_counter()
            selected: list[str] = []
            status = "COMPLETE"
            error_code = None
            try:
                result = _optional_selection(slot, provider, task, candidate_ids, metadata, revision)
                selected = _select_ids(result, candidate_ids)
                actual_ids.add(result.provider_id)
                measured_latencies.append(round((perf_counter() - started) * 1000, 3))
            except Exception as error:  # provider failures are bounded evidence
                status = "NOT_MEASURED" if str(getattr(provider, "provider_id", "")).startswith("unavailable") else "ERROR"
                error_code = getattr(error, "error_code", None)
                if not isinstance(error_code, str) or not error_code:
                    error_code = type(error).__name__
                error_code = re.sub(r"[^A-Za-z0-9_.-]", "_", error_code)[:64]
                error_codes.append(error_code)
                actual_ids.add(str(getattr(provider, "provider_id", "unavailable")))
            answerability = _answerability(document)
            safety = _safety(task, selected, metadata)
            safety_total.update(safety)
            row: dict[str, Any] = {
                "task_id": task.task_id,
                "answerability": answerability["status"],
                "provider_status": status,
                "selected_ids": selected,
                "selected_count": len(selected),
                "latency_ms": round((perf_counter() - started) * 1000, 3),
                "safety": safety,
            }
            if answerability["status"] == "answerable" and status == "COMPLETE":
                row["metrics"] = _metric_rows(selected, document, metadata)
            else:
                row["metrics"] = None
            if error_code:
                row["error_code"] = error_code
            rows.append(row)
    if len(source_values) != 1:
        raise W06C0Error(f"provider {slot} did not receive one candidate snapshot")
    revision, content_fp, order_fp = next(iter(source_values))
    answer_counts = Counter(row["answerability"] for row in rows)
    scored = [row for row in rows if row["metrics"] is not None]
    actual_provider = sorted(actual_ids)[0] if len(actual_ids) == 1 else requested_id
    all_unavailable = bool(rows) and all(row["provider_status"] == "NOT_MEASURED" for row in rows)
    return {
        "slot": slot,
        "requested_provider_id": requested_id,
        "actual_provider_id": actual_provider,
        "model": model,
        "availability": "UNAVAILABLE" if all_unavailable else "AVAILABLE",
        "run_status": "NOT_MEASURED" if all_unavailable else ("ERROR" if error_codes else "COMPLETE"),
        "fallback": False,
        "provider_schema_version": 1,
        "error_code": error_codes[0] if error_codes else None,
        "case_count": len(rows),
        "scored_count": len(scored),
        "excluded_counts": {name: answer_counts.get(name, 0) for name in sorted(STATUSES)},
        "metrics": _averages(scored),
        "quality_state": "INSUFFICIENT_ANSWERABLE_CASES" if not scored else "MEASURED",
        "safety": dict(sorted(safety_total.items())),
        "latency_ms": {
            "p50": statistics.median(measured_latencies) if measured_latencies else None,
            "p95": measured_latencies[max(0, math.ceil(len(measured_latencies) * 0.95) - 1)] if measured_latencies else None,
        },
        "source_memory_revision": revision,
        "candidate_content_fingerprint": content_fp,
        "candidate_order_fingerprint": order_fp,
        "rows": rows,
    }


def _averages(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    names = ("precision", "recall", "f1", "mrr", "mandatory_recall", "noise_ratio", "token_waste")
    output: dict[str, Any] = {}
    for k in K_VALUES:
        values = [row["metrics"][str(k)] for row in rows if row.get("metrics") and str(k) in row["metrics"]]
        output[str(k)] = {
            name: (sum(float(item[name]) for item in values if item[name] is not None) /
                   len([item for item in values if item[name] is not None])
                   if any(item[name] is not None for item in values) else None)
            for name in names
        }
    return output


def _run_core_provider(
    slot: str,
    documents: Sequence[Mapping[str, Any]],
    tasks: Sequence[GoldenTask],
    fixture: Any,
) -> dict[str, Any]:
    provider, requested_id = _provider(slot)
    rows: list[dict[str, Any]] = []
    safety_total = Counter()
    source_values: set[tuple[Any, ...]] = set()
    unavailable = False
    actual_ids: set[str] = set()
    with tempfile.TemporaryDirectory(prefix=f"brain-eleven-w06c0-{slot}-") as directory:
        for document, task in zip(documents, tasks):
            vault = Path(directory) / task.task_id
            build_vault(fixture, vault, seed=SEED, noise_count=NOISE_COUNT)
            revision, candidate_ids, metadata, content_fp, order_fp = _snapshot(vault)
            source_values.add((revision, content_fp, order_fp))
            started = perf_counter()
            selected: list[str] = []
            status = "COMPLETE"
            error_code = None
            try:
                result = provider.select(task, vault)
                selected = _select_ids(result, candidate_ids)
                actual_id = result.provider_id
                actual_ids.add(actual_id)
            except Exception as error:  # provider failures are bounded evidence
                status = "ERROR"
                error_code = type(error).__name__
                actual_id = requested_id
                actual_ids.add(actual_id)
                unavailable = True
            elapsed_ms = round((perf_counter() - started) * 1000, 3)
            answerability = _answerability(document)
            safety = _safety(task, selected, metadata)
            safety_total.update(safety)
            row: dict[str, Any] = {
                "task_id": task.task_id,
                "answerability": answerability["status"],
                "provider_status": status,
                "selected_ids": selected,
                "selected_count": len(selected),
                "latency_ms": elapsed_ms,
                "safety": safety,
            }
            if answerability["status"] == "answerable" and status == "COMPLETE":
                row["metrics"] = _metric_rows(selected, document, metadata)
            else:
                row["metrics"] = None
            if error_code:
                row["error_code"] = error_code
            rows.append(row)
    if len(source_values) != 1:
        raise W06C0Error(f"provider {slot} did not receive one candidate snapshot")
    revision, content_fp, order_fp = next(iter(source_values))
    answer_counts = Counter(row["answerability"] for row in rows)
    scored = [row for row in rows if row["metrics"] is not None]
    latencies = sorted(float(row["latency_ms"]) for row in rows)
    return {
        "slot": slot,
        "requested_provider_id": slot,
        "actual_provider_id": sorted(actual_ids)[0] if len(actual_ids) == 1 else requested_id,
        "model": "existing_adapter",
        "availability": "AVAILABLE" if not unavailable else "AVAILABLE",
        "run_status": "COMPLETE" if not unavailable else "ERROR",
        "fallback": bool(actual_ids and actual_ids != {requested_id}),
        "provider_schema_version": 1,
        "error_code": "PROVIDER_CASE_ERROR" if unavailable else None,
        "case_count": len(rows),
        "scored_count": len(scored),
        "excluded_counts": {name: answer_counts.get(name, 0) for name in sorted(STATUSES)},
        "metrics": _averages(scored),
        "quality_state": "INSUFFICIENT_ANSWERABLE_CASES" if not scored else "MEASURED",
        "safety": dict(sorted(safety_total.items())),
        "latency_ms": {
            "p50": statistics.median(latencies) if latencies else None,
            "p95": latencies[max(0, math.ceil(len(latencies) * 0.95) - 1)] if latencies else None,
        },
        "source_memory_revision": revision,
        "candidate_content_fingerprint": content_fp,
        "candidate_order_fingerprint": order_fp,
        "rows": rows,
    }


def run_matrix(
    *,
    split: str = "dev",
    providers: Sequence[str] = PROVIDER_SLOTS,
    corpus_root: Path | str = CORPUS_ROOT,
    measure_optional: bool = False,
    allow_holdout: bool = False,
) -> dict[str, Any]:
    """Run one content-free provider matrix on one immutable v3 split."""

    if split == "holdout" and not allow_holdout:
        raise W06C0Error("holdout requires explicit final-audit confirmation")
    unknown = set(providers) - set(PROVIDER_SLOTS)
    if unknown:
        raise W06C0Error(f"unknown provider slots: {sorted(unknown)}")
    documents, tasks, manifest = load_corpus(split, corpus_root)
    fixture = load_fixture(FIXTURE_PATH)
    results: dict[str, Any] = {}
    with tempfile.TemporaryDirectory(prefix="brain-eleven-w06c0-snapshot-") as snapshot_directory:
        snapshot_vault = Path(snapshot_directory) / "vault"
        build_vault(fixture, snapshot_vault, seed=SEED, noise_count=NOISE_COUNT)
        revision, _, _, content_fp, order_fp = _snapshot(snapshot_vault)
        snapshot = (revision, content_fp, order_fp)
    for slot in providers:
        if slot in {"embedding", "reranker"}:
            # Optional model slots remain offline by default.  An explicit
            # probe may measure the configured real adapter; unavailable
            # adapters remain an honest NOT_MEASURED result.
            results[slot] = (
                _run_optional_provider(slot, documents, tasks, fixture)
                if measure_optional
                else _empty_optional(slot, documents, snapshot)
            )
            continue
        results[slot] = _run_core_provider(slot, documents, tasks, fixture)
    snapshots = {
        (result.get("source_memory_revision"), result.get("candidate_content_fingerprint"), result.get("candidate_order_fingerprint"))
        for result in results.values() if result.get("source_memory_revision") is not None
    }
    if len(snapshots) > 1:
        raise W06C0Error("provider candidate snapshot fingerprints differ")
    return {
        "schema_version": 1,
        "report_type": "brain_eleven_w06c0_feasibility",
        "corpus": {
            "version": CORPUS_VERSION,
            "split": split,
            "case_count": len(documents),
            "manifest_sha256": manifest["manifest_sha256"],
            "split_fingerprint": manifest["split_fingerprints"][split],
            "excluded_counts": {
                status: sum(_answerability(document)["status"] == status for document in documents)
                for status in sorted(STATUSES)
            },
        },
        "source": {
            "source_fingerprint": source_fingerprint(),
            "seed": SEED,
            "noise_count": NOISE_COUNT,
            "k_values": list(K_VALUES),
            "holdout_included": split == "holdout",
        },
        "providers": results,
        "quality": {
            "state": (
                "INSUFFICIENT_ANSWERABLE_CASES"
                if not any(_answerability(document)["status"] == "answerable" for document in documents)
                else "MEASURED"
            ),
            "answerable_count": sum(_answerability(document)["status"] == "answerable" for document in documents),
        },
        "promotion": "blocked",
        "production_mutation": False,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the W-06C0 evaluation-only feasibility matrix")
    parser.add_argument("--split", choices=SPLITS, default="dev")
    parser.add_argument("--providers", nargs="+", choices=PROVIDER_SLOTS, default=list(PROVIDER_SLOTS))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--final-holdout", action="store_true")
    parser.add_argument("--measure-optional", action="store_true")
    args = parser.parse_args(argv)
    report = run_matrix(
        split=args.split,
        providers=args.providers,
        allow_holdout=args.final_holdout,
        measure_optional=args.measure_optional,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "output": str(args.output),
        "split": args.split,
        "case_count": report["corpus"]["case_count"],
        "excluded_counts": report["corpus"]["excluded_counts"],
        "providers": sorted(report["providers"]),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
