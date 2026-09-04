"""Build and verify the frozen 160-task Phase 15 corpus-v2.

V2 deliberately lives beside the historical corpus.  It owns every task it
writes, which makes the public/holdout split and taxonomy auditable without
rewriting the inputs used to produce baseline-v1.
"""

from __future__ import annotations

import argparse
import json
from copy import deepcopy
from pathlib import Path
from typing import Any, Mapping, Sequence

from .corpus_builder import (
    CorpusBuildError,
    _ACTIVE_PROJECTS,
    _GLOBAL,
    _foreign_project,
    _inactive_memory,
    _project_for,
    _project_memory,
    _task_document,
    _render,
    public_task_documents,
)
from .schema import VaultFixture, load_fixture, validate_task_documents


CORPUS_VERSION = 2
TASK_PREFIX = "p15_"
EXPECTED_SUITE_COUNTS = {"dev": 70, "test": 60, "holdout": 30}
EXPECTED_TASK_COUNT = sum(EXPECTED_SUITE_COUNTS.values())
_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FIXTURE_PATH = _ROOT / "evals" / "fixtures" / "phase15-contract.json"
DEFAULT_CORPUS_ROOT = _ROOT / "evals" / "corpus-v2"
TAXONOMY = (
    "basic_relevance", "lexical_traps", "same_domain_wrong_project",
    "global_project", "supersession", "resolved_lifecycle", "archived_project",
    "noise_heavy", "ambiguity", "duplicate_semantics", "contradiction",
    "authority_traps", "state_relevance", "cross_phase_traps", "secret_forbidden",
    "malicious_input",
)


def _legacy_atomic_document() -> dict[str, Any]:
    return _task_document(
        task_id="p15_persistence_001",
        project_id="eleven_capture",
        prompt="Quick Note kaydetme akışında Markdown ve SQLite write ordering nasıl olmalı?",
        required=["mem_markdown_source_of_truth", "mem_markdown_before_sqlite"],
        useful=["mem_windows_target"],
        forbidden=["mem_promtgen_storage", "mem_superseded_save_rule"],
        intent=["architecture", "persistence"],
        domains=["filesystem", "sqlite", "reliability"],
        expectations={"authority_resolution": "future", "conflict_resolution": "future", "ask_user": False, "abstain": False},
    )


def _extension_document(index: int, suite: str, category: str) -> tuple[Path, dict[str, Any]]:
    project = _project_for(index)
    foreign = _foreign_project(project)
    primary = _project_memory(project, index)
    global_memory = _GLOBAL[(index - 1) % len(_GLOBAL)]
    prompt_templates = (
        "{project} için {category} bağlamında güvenli aktif kararı seç.",
        "Select only active {project} context for the {category} evaluation case.",
        "{project} scope içinde {category} decision'ını değerlendir; foreign context kullanma.",
    )
    required = [primary]
    useful = [global_memory]
    if category in {"global_project", "state_relevance", "cross_phase_traps"}:
        required = [global_memory, primary]
    if category == "ambiguity":
        project = None
        required = [global_memory]
        useful = [_GLOBAL[index % len(_GLOBAL)]]
    if category == "secret_forbidden":
        required = ["mem_secret_redaction"]
    document = _task_document(
        task_id=f"p15_v2_{category}_{index:03d}",
        project_id=project,
        prompt=prompt_templates[(index - 1) % len(prompt_templates)].format(project=project or "global", category=category.replace("_", " ")),
        required=required,
        useful=useful,
        forbidden=[_project_memory(foreign, index), _inactive_memory(project or _ACTIVE_PROJECTS[0], index)],
        intent=["architecture" if index % 2 else "review"],
        domains=[category, "reliability"],
        expectations={"authority_resolution": "future", "conflict_resolution": "future", "ask_user": False, "abstain": False},
    )
    return Path(suite) / f"p15_v2_{category}_{index:03d}.json", document


def corpus_v2_documents() -> dict[Path, dict[str, Any]]:
    """Return the complete deterministic V2 corpus with exact suite boundaries."""

    documents = deepcopy(public_task_documents())
    documents[Path("dev") / "p15_persistence_001.json"] = _legacy_atomic_document()
    current = {suite: sum(path.parts[0] == suite for path in documents) for suite in EXPECTED_SUITE_COUNTS}
    extensions: list[tuple[str, str]] = []
    for suite, target in EXPECTED_SUITE_COUNTS.items():
        extensions.extend((suite, TAXONOMY[offset % len(TAXONOMY)]) for offset in range(target - current[suite]))
    for index, (suite, category) in enumerate(extensions, start=1):
        relative, document = _extension_document(index, suite, category)
        if relative in documents:
            raise CorpusBuildError(f"duplicate V2 task path: {relative}")
        documents[relative] = document
    counts = {suite: sum(path.parts[0] == suite for path in documents) for suite in EXPECTED_SUITE_COUNTS}
    if len(documents) != EXPECTED_TASK_COUNT or counts != EXPECTED_SUITE_COUNTS:
        raise CorpusBuildError(f"invalid V2 corpus shape: count={len(documents)}, suites={counts}")
    return documents


def corpus_v2_manifest() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "corpus_version": CORPUS_VERSION,
        "task_count": EXPECTED_TASK_COUNT,
        "suite_counts": EXPECTED_SUITE_COUNTS,
        "taxonomy": list(TAXONOMY),
        "languages": ["turkish", "english", "mixed"],
        "privacy": "synthetic_only",
        "document_categories": ["historical_coverage", *TAXONOMY],
    }


def validate_corpus_v2_documents(fixture: VaultFixture) -> dict[Path, dict[str, Any]]:
    documents = corpus_v2_documents()
    validate_task_documents(documents.values(), fixture)
    return documents


def write_corpus_v2(corpus_root: Path | str, fixture: VaultFixture) -> tuple[Path, ...]:
    root = Path(corpus_root)
    documents = validate_corpus_v2_documents(fixture)
    written: list[Path] = []
    for relative, document in documents.items():
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(_render(document), encoding="utf-8")
        written.append(target)
    (root / "manifest.json").write_text(json.dumps(corpus_v2_manifest(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return tuple(sorted(written))


def check_corpus_v2(corpus_root: Path | str, fixture: VaultFixture) -> None:
    root = Path(corpus_root)
    documents = validate_corpus_v2_documents(fixture)
    expected = {root / path for path in documents}
    actual = set(root.rglob(f"{TASK_PREFIX}*.json")) if root.exists() else set()
    if actual != expected:
        raise CorpusBuildError("V2 corpus paths differ from the deterministic source")
    for relative, document in documents.items():
        if (root / relative).read_text(encoding="utf-8") != _render(document):
            raise CorpusBuildError(f"V2 corpus content differs: {relative}")
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    if manifest != corpus_v2_manifest():
        raise CorpusBuildError("V2 corpus manifest differs from the deterministic source")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build or verify the synthetic Phase 15 corpus-v2.")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE_PATH)
    parser.add_argument("--corpus-root", type=Path, default=DEFAULT_CORPUS_ROOT)
    args = parser.parse_args(argv)
    fixture = load_fixture(args.fixture)
    if args.write:
        print(json.dumps({"written": len(write_corpus_v2(args.corpus_root, fixture)), "corpus_version": CORPUS_VERSION}, sort_keys=True))
    else:
        check_corpus_v2(args.corpus_root, fixture)
        print(json.dumps({"status": "current", "corpus_version": CORPUS_VERSION}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
