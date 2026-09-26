"""Measure MPNet retrieval against a small, real-vault-derived corpus.

Evaluation-only, exactly like ``evals/ig01d/spike.py`` and
``evals/ig01d/d0_recheck.py`` next to it: no production retrieval path is
imported or mutated, and this module owns no canonical write path.

Why this exists: ``D0-RECHECK-FINDINGS.md`` traced the D0/D1 precision
numbers to a corpus (``evals/corpus-v2``) that is entirely synthetic on both
sides of the measurement -- 40 mechanically templated task prompts *and* a
hand-authored, English-only, fictional 38-record memory fixture
(``evals/fixtures/phase15-contract.json``). Three embedding models measured
against that corpus converged in a narrow, unremarkable band (BGE-M3 0.1867,
E5-large ~0.19, MPNet 0.2597 corrected) -- consistent with the corpus itself,
not the model, being the limiting factor. This probe re-measures the
best-performing model (MPNet) against a corpus built from real vault content
(``evals/ig01e_real/fixtures/real-content-v1.json``, ``tasks/*.json``) using
the exact same corrected metric (``precision@min(5,|relevant|)``) so the two
numbers are directly comparable.

Reuses ``evals.ig01d.spike`` (candidate filtering, semantic ranking) and
``evals.ig01d.d0_recheck`` (the corrected metric, safety-leakage counting)
without modifying either file.
"""

from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path
from typing import Any

from brain_eleven.retrieval.embedding_provider import (
    EmbeddingProvider,
    LocalCrossEncoderReranker,
    LocalSentenceTransformerProvider,
    Reranker,
)

from ..fixture_generator import build_vault
from ..schema import load_fixture, load_tasks
from ..ig01d.d0_recheck import _aggregate_recheck, _metric_row_recheck
from ..ig01d.d0_rethink import _safety_counts
from ..ig01d.spike import _K, _allowed_records, _rank_semantic, _read_records


ROOT = Path(__file__).resolve().parents[2]
FIXTURE_PATH = Path(__file__).resolve().parent / "fixtures" / "real-content-v1.json"
TASKS_DIR = Path(__file__).resolve().parent / "tasks"
SEED = 0
NOISE_COUNT = 0  # real cross-project/superseded content already provides distractors


def _git_sha(root: Path) -> str:
    import subprocess

    return subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        check=True, capture_output=True, text=True,
    ).stdout.strip().lower()


def run_real_probe(
    *,
    embedding_provider: EmbeddingProvider,
    reranker: Reranker,
    fixture_path: Path = FIXTURE_PATH,
    tasks_dir: Path = TASKS_DIR,
) -> dict[str, Any]:
    fixture = load_fixture(fixture_path)
    task_paths = sorted(tasks_dir.glob("*.json"))
    tasks = load_tasks(task_paths, fixture)
    documents = [json.loads(path.read_text(encoding="utf-8")) for path in task_paths]

    rows: list[dict[str, Any]] = []
    from collections import Counter

    safety_counter: Counter[str] = Counter()
    provider_identity: dict[str, Any] = {}

    with tempfile.TemporaryDirectory(prefix="brain-eleven-ig01e-real-") as directory:
        vault = build_vault(fixture, Path(directory) / "vault", seed=SEED, noise_count=NOISE_COUNT)
        records = _read_records(vault.root)
        for document, task in zip(documents, tasks):
            selected_ids, identity = _rank_semantic(
                task=task,
                records=records,
                embedding_provider=embedding_provider,
                reranker=reranker,
            )
            provider_identity = identity
            required = tuple(document["expected_context"]["required"])
            useful = tuple(document["expected_context"]["useful"])
            forbidden = set(document["expected_context"]["forbidden"])
            metrics = _metric_row_recheck(selected_ids, required, useful)
            rows.append({"task_id": task.task_id, **metrics})
            safety_counter.update(_safety_counts(selected_ids, records, task, forbidden))

    oracle_scores = [
        min(len(set(doc["expected_context"]["required"]) | set(doc["expected_context"]["useful"])), _K) / _K
        for doc in documents
    ]
    oracle_precision_at_5 = sum(oracle_scores) / len(oracle_scores) if oracle_scores else None

    return {
        "schema_version": 1,
        "report_type": "ig01e_real_content_probe",
        "source": {
            "git_sha": _git_sha(ROOT),
            "corpus": "ig01e_real/real-content-v1",
            "case_count": len(tasks),
            "seed": SEED,
            "noise_count": NOISE_COUNT,
            "k": _K,
        },
        "provider_identity": provider_identity,
        "oracle_precision_at_5": oracle_precision_at_5,
        "metrics": _aggregate_recheck(rows),
        "per_case": rows,
        "safety": dict(sorted(safety_counter.items())),
        "production_mutation": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Measure MPNet against the real-vault-derived ig01e corpus")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--embedding-model",
        default="sentence-transformers/paraphrase-multilingual-mpnet-base-v2",
    )
    parser.add_argument(
        "--reranker-model",
        default="cross-encoder/mmarco-mMiniLMv2-L12-H384-v1",
    )
    parser.add_argument("--local-files-only", action="store_true")
    args = parser.parse_args(argv)

    embedding: EmbeddingProvider = LocalSentenceTransformerProvider(
        args.embedding_model, local_files_only=args.local_files_only,
    )
    reranker: Reranker = LocalCrossEncoderReranker(
        args.reranker_model, local_files_only=args.local_files_only,
    )

    result = run_real_probe(embedding_provider=embedding, reranker=reranker)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "output": str(args.output),
        "case_count": result["source"]["case_count"],
        "oracle_precision_at_5": result["oracle_precision_at_5"],
        "precision_at_min5_relevant": result["metrics"]["precision_at_min5_relevant"],
        "safety": result["safety"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
