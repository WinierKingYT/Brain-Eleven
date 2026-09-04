"""Generate the public, synthetic Phase 15 golden-task corpus deterministically.

The emitted JSON files are versioned fixtures, not runtime data. This builder
keeps their category coverage, suite split, and stable task IDs checkable in CI.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from .schema import VaultFixture, load_fixture, validate_task_documents


PUBLIC_CORPUS_VERSION = 1
GENERATED_TASK_PREFIX = "p15_"
EXPECTED_PUBLIC_TASK_COUNT = 108
EXPECTED_SUITE_COUNTS = {"dev": 53, "test": 47, "holdout": 8}
_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FIXTURE_PATH = _ROOT / "evals" / "fixtures" / "phase15-contract.json"
DEFAULT_CORPUS_ROOT = _ROOT / "evals" / "corpus"

_ACTIVE_PROJECTS = ("eleven_capture", "promtgen", "minecraft_mcp")
_GLOBAL = (
    "mem_markdown_source_of_truth",
    "mem_atomic_replace",
    "mem_file_lock",
    "mem_restore_rebuild",
    "mem_default_scope",
    "mem_secret_redaction",
    "mem_utf8_paths",
    "mem_backup_canonical",
    "mem_stale_projection",
    "mem_explicit_decision",
    "mem_context_budget",
    "mem_schema_version",
    "mem_no_network",
    "mem_windows_target",
)
_ACTIVE = {
    "eleven_capture": (
        "mem_markdown_before_sqlite",
        "mem_ec_sqlite_index",
        "mem_ec_vault_manifest",
        "mem_ec_local_cache",
        "mem_ec_atomic_rename",
    ),
    "promtgen": (
        "mem_promtgen_storage",
        "mem_pg_prompt_versioning",
        "mem_pg_indexeddb_backup",
        "mem_pg_template_contract",
        "mem_pg_redis_cache",
    ),
    "minecraft_mcp": (
        "mem_mc_protocol_version",
        "mem_mc_world_backup",
        "mem_mc_command_policy",
        "mem_mc_event_stream",
    ),
}
_INACTIVE = {
    "eleven_capture": ("mem_superseded_save_rule", "mem_ec_resolved_json_cache"),
    "promtgen": ("mem_pg_old_localstorage", "mem_pg_resolved_cdn"),
    "minecraft_mcp": ("mem_mc_old_websocket", "mem_mc_resolved_polling"),
}


class CorpusBuildError(ValueError):
    """Raised when generated public-corpus paths are incomplete or unsafe."""


def _dedupe(values: Iterable[str]) -> list[str]:
    """Preserve deterministic order while removing shared scenario labels."""

    return list(dict.fromkeys(values))


def _task_document(
    *,
    task_id: str,
    project_id: str | None,
    prompt: str,
    required: Iterable[str],
    useful: Iterable[str],
    forbidden: Iterable[str],
    intent: Iterable[str],
    domains: Iterable[str],
    expectations: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    required_labels = _dedupe(required)
    useful_labels = [item for item in _dedupe(useful) if item not in required_labels]
    forbidden_labels = [
        item
        for item in _dedupe(forbidden)
        if item not in required_labels and item not in useful_labels
    ]
    document: dict[str, Any] = {
        "schema_version": PUBLIC_CORPUS_VERSION,
        "task_id": task_id,
        "task": {
            "project_id": project_id,
            "prompt": prompt,
            "intent": list(intent),
            "domains": list(domains),
        },
        "expected_context": {
            "required": required_labels,
            "useful": useful_labels,
            "forbidden": forbidden_labels,
        },
        "expected_behavior": {
            "wrong_project_allowed": False,
            "inactive_allowed": False,
        },
    }
    if expectations is not None:
        document["expectations"] = dict(expectations)
    return document


def _project_for(index: int) -> str:
    return _ACTIVE_PROJECTS[(index - 1) % len(_ACTIVE_PROJECTS)]


def _foreign_project(project_id: str) -> str:
    return _ACTIVE_PROJECTS[(_ACTIVE_PROJECTS.index(project_id) + 1) % len(_ACTIVE_PROJECTS)]


def _project_memory(project_id: str, index: int) -> str:
    choices = _ACTIVE[project_id]
    return choices[(index - 1) % len(choices)]


def _inactive_memory(project_id: str, index: int) -> str:
    choices = _INACTIVE[project_id]
    return choices[(index - 1) % len(choices)]


def public_task_documents() -> dict[Path, dict[str, Any]]:
    """Return every generated task under its safe corpus-relative path."""

    documents: dict[Path, dict[str, Any]] = {}

    def emit(suite: str, category: str, index: int, **kwargs: Any) -> None:
        relative = Path(suite) / f"{GENERATED_TASK_PREFIX}{category}_{index:03d}.json"
        if relative in documents:
            raise CorpusBuildError(f"duplicate generated path: {relative}")
        documents[relative] = _task_document(
            task_id=f"{GENERATED_TASK_PREFIX}{category}_{index:03d}", **kwargs
        )

    for index in range(1, 25):
        project = _project_for(index)
        foreign_project = _foreign_project(project)
        emit(
            "dev",
            "relevance",
            index,
            project_id=project,
            prompt=f"Select the reliable persistence rule for {project} relevance scenario {index}.",
            required=[_project_memory(project, index)],
            useful=[_GLOBAL[(index - 1) % len(_GLOBAL)]],
            forbidden=[_project_memory(foreign_project, index), _inactive_memory(project, index)],
            intent=["architecture"],
            domains=["reliability"],
        )

    for index in range(1, 21):
        project = _project_for(index)
        foreign_project = _foreign_project(project)
        emit(
            "dev" if index <= 12 else "test",
            "project_isolation",
            index,
            project_id=project,
            prompt=f"Retrieve only {project} context for isolation scenario {index}.",
            required=[_project_memory(project, index)],
            useful=["mem_default_scope"],
            forbidden=[
                _project_memory(foreign_project, index),
                "mem_legacy_export",
                _inactive_memory(project, index),
            ],
            intent=["scope"],
            domains=["project-isolation"],
        )

    for index in range(1, 15):
        project = _project_for(index)
        emit(
            "test",
            "lifecycle",
            index,
            project_id=project,
            prompt=f"Use active {project} state while excluding completed lifecycle records {index}.",
            required=[_project_memory(project, index)],
            useful=["mem_stale_projection"],
            forbidden=[_inactive_memory(project, index), _inactive_memory(project, index + 1)],
            intent=["lifecycle"],
            domains=["memory-lifecycle"],
        )

    replacements = (
        ("eleven_capture", "mem_markdown_before_sqlite", "mem_superseded_save_rule"),
        ("eleven_capture", "mem_ec_atomic_rename", "mem_ec_resolved_json_cache"),
        ("promtgen", "mem_pg_prompt_versioning", "mem_pg_old_localstorage"),
        ("promtgen", "mem_pg_template_contract", "mem_pg_resolved_cdn"),
        ("minecraft_mcp", "mem_mc_command_policy", "mem_mc_old_websocket"),
        ("minecraft_mcp", "mem_mc_world_backup", "mem_mc_resolved_polling"),
    )
    for index in range(1, 13):
        project, active, inactive = replacements[(index - 1) % len(replacements)]
        emit(
            "test",
            "supersession",
            index,
            project_id=project,
            prompt=f"Resolve the authoritative replacement rule for {project} scenario {index}.",
            required=[active],
            useful=["mem_explicit_decision"],
            forbidden=[inactive],
            intent=["supersession"],
            domains=["authority"],
        )

    for index in range(1, 11):
        project = _project_for(index)
        foreign_project = _foreign_project(project)
        emit(
            "dev" if index <= 8 else "test",
            "global_project",
            index,
            project_id=project,
            prompt=f"Combine global engineering rules with {project} decisions for scenario {index}.",
            required=[_GLOBAL[(index - 1) % len(_GLOBAL)], _project_memory(project, index)],
            useful=["mem_context_budget"],
            forbidden=[_project_memory(foreign_project, index), "mem_legacy_import"],
            intent=["architecture", "scope"],
            domains=["global", "project"],
        )

    for index in range(1, 9):
        emit(
            "test" if index <= 4 else "holdout",
            "ambiguity",
            index,
            project_id=None,
            prompt=f"Answer only from global policy while current project is ambiguous {index}.",
            required=[_GLOBAL[(index - 1) % len(_GLOBAL)]],
            useful=[_GLOBAL[index % len(_GLOBAL)]],
            forbidden=[
                _project_memory("eleven_capture", index),
                _project_memory("promtgen", index),
                _project_memory("minecraft_mcp", index),
                "mem_legacy_export",
            ],
            intent=["ambiguity"],
            domains=["scope"],
        )

    for index in range(1, 9):
        project = _project_for(index)
        foreign_project = _foreign_project(project)
        emit(
            "dev" if index <= 6 else "test",
            "noise",
            index,
            project_id=project,
            prompt=f"Find essential context from a noise-heavy {project} vault scenario {index}.",
            required=[_project_memory(project, index), _GLOBAL[(index + 2) % len(_GLOBAL)]],
            useful=[],
            forbidden=[_project_memory(foreign_project, index), _inactive_memory(project, index)],
            intent=["relevance"],
            domains=["noise", "ranking"],
        )

    for index in range(1, 7):
        project, active, inactive = replacements[(index - 1) % len(replacements)]
        emit(
            "test" if index <= 3 else "holdout",
            "conflict",
            index,
            project_id=project,
            prompt=f"Select the non-conflicting current decision for {project} scenario {index}.",
            required=[active],
            useful=["mem_explicit_decision"],
            forbidden=[inactive, _project_memory(_foreign_project(project), index)],
            intent=["conflict"],
            domains=["decision"],
            expectations={"conflict_resolution": "future", "ask_user": False, "abstain": False},
        )

    for index in range(1, 7):
        project = _project_for(index)
        foreign_project = _foreign_project(project)
        emit(
            "dev" if index <= 3 else "test" if index <= 5 else "holdout",
            "authority_future",
            index,
            project_id=project,
            prompt=f"Record the future authority decision case for {project} scenario {index}.",
            required=[_project_memory(project, index)],
            useful=["mem_explicit_decision"],
            forbidden=[_inactive_memory(project, index), _project_memory(foreign_project, index)],
            intent=["authority"],
            domains=["future-capability"],
            expectations={
                "authority_resolution": "future",
                "conflict_resolution": "future",
                "ask_user": False,
                "abstain": False,
            },
        )

    if len(documents) != EXPECTED_PUBLIC_TASK_COUNT:
        raise CorpusBuildError(
            f"expected {EXPECTED_PUBLIC_TASK_COUNT} generated tasks, got {len(documents)}"
        )
    suite_counts = {suite: sum(path.parts[0] == suite for path in documents) for suite in EXPECTED_SUITE_COUNTS}
    if suite_counts != EXPECTED_SUITE_COUNTS:
        raise CorpusBuildError(f"unexpected suite counts: {suite_counts}")
    return documents


def validate_public_task_documents(fixture: VaultFixture) -> dict[Path, dict[str, Any]]:
    """Validate generated documents through the same corpus contract as CI."""

    documents = public_task_documents()
    validate_task_documents(documents.values(), fixture)
    return documents


def _render(document: Mapping[str, Any]) -> str:
    return json.dumps(document, indent=2, ensure_ascii=False) + "\n"


def write_public_corpus(corpus_root: Path | str, fixture: VaultFixture) -> tuple[Path, ...]:
    """Write only deterministic ``p15_*.json`` files below a chosen corpus root."""

    root = Path(corpus_root)
    documents = validate_public_task_documents(fixture)
    written: list[Path] = []
    for relative, document in documents.items():
        if relative.is_absolute() or ".." in relative.parts:
            raise CorpusBuildError(f"unsafe generated corpus path: {relative}")
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        rendered = _render(document)
        if not target.exists() or target.read_text(encoding="utf-8") != rendered:
            target.write_text(rendered, encoding="utf-8")
            written.append(target)
    return tuple(written)


def check_public_corpus(corpus_root: Path | str, fixture: VaultFixture) -> None:
    """Raise unless generated public tasks exist exactly as their source specifies."""

    root = Path(corpus_root)
    documents = validate_public_task_documents(fixture)
    expected_paths = {root / relative for relative in documents}
    actual_paths = set(root.rglob(f"{GENERATED_TASK_PREFIX}*.json")) if root.exists() else set()
    if actual_paths != expected_paths:
        missing = sorted(str(path.relative_to(root)) for path in expected_paths - actual_paths)
        unexpected = sorted(str(path.relative_to(root)) for path in actual_paths - expected_paths)
        raise CorpusBuildError(f"generated corpus paths differ; missing={missing}, unexpected={unexpected}")
    mismatched = [
        str(relative)
        for relative, document in documents.items()
        if (root / relative).read_text(encoding="utf-8") != _render(document)
    ]
    if mismatched:
        raise CorpusBuildError(f"generated corpus content differs: {mismatched}")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build or verify the public Phase 15 golden corpus.")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true", help="write deterministic managed task files")
    mode.add_argument("--check", action="store_true", help="verify managed task files without writing")
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE_PATH)
    parser.add_argument("--corpus-root", type=Path, default=DEFAULT_CORPUS_ROOT)
    args = parser.parse_args(argv)

    fixture = load_fixture(args.fixture)
    if args.write:
        written = write_public_corpus(args.corpus_root, fixture)
        print(json.dumps({"generated_tasks": EXPECTED_PUBLIC_TASK_COUNT, "written": len(written)}, sort_keys=True))
    else:
        check_public_corpus(args.corpus_root, fixture)
        print(json.dumps({"generated_tasks": EXPECTED_PUBLIC_TASK_COUNT, "status": "current"}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
