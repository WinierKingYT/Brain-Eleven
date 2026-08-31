#!/usr/bin/env python3
"""Safely capture one memory from any project into Brain-Eleven.

This module is intentionally a thin adapter around the existing validator and
entity-extraction pipeline. Manual capture is always allowed when explicitly
invoked; proactive capture must call :func:`is_project_opted_in` first.

Project provenance is stored as a short, caller-visible identifier by default
(usually the current directory name), not as an absolute filesystem path. The
absolute path is used only for opt-in matching and is never persisted by this
module unless the caller explicitly supplies it as ``project``.
"""

import argparse
import importlib.util
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from memory_scope import (
    GLOBAL_SCOPE,
    PROJECT_SCOPE,
    project_identity,
    resolve_capture_scope,
)
from project_registry import ProjectRegistry, registry_path as project_registry_path


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_VAULT = SCRIPT_DIR.parent
def _load_hyphenated_module(name: str, filename: str):
    """Load one of Brain-Eleven's legacy hyphenated module filenames."""
    spec = importlib.util.spec_from_file_location(name, SCRIPT_DIR / filename)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load {filename}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

_memory_validator = _load_hyphenated_module("memory_validator", "memory-validator.py")
MemoryValidator = _memory_validator.MemoryValidator
EntityExtractor = _load_hyphenated_module("entity_extractor", "entity_extractor.py").EntityExtractor


def default_vault_path() -> Path:
    """Return the configured vault, defaulting to this repository."""
    configured = os.environ.get("BRAIN_ELEVEN_VAULT_PATH")
    return Path(configured).expanduser() if configured else DEFAULT_VAULT


def default_project_id(project_root: Optional[Union[str, Path]] = None) -> str:
    """Return a privacy-preserving project identifier for stored memories."""
    return project_identity(project_root)[1]


def is_project_opted_in(
    project_root: Optional[Union[str, Path]] = None,
    vault_path: Optional[Union[str, Path]] = None,
) -> bool:
    """Return the canonical fail-closed proactive-capture decision."""
    vault = Path(vault_path).expanduser() if vault_path else default_vault_path()
    return ProjectRegistry(vault).proactive_capture_policy(project_root or Path.cwd())["allowed"]


def proactive_capture_policy(
    project_root: Optional[Union[str, Path]] = None,
    vault_path: Optional[Union[str, Path]] = None,
) -> Dict[str, Any]:
    """Expose the canonical registry policy without leaking a filesystem root."""
    vault = Path(vault_path).expanduser() if vault_path else default_vault_path()
    return ProjectRegistry(vault).proactive_capture_policy(project_root or Path.cwd())


def remember(
    type_: str,
    content: str,
    confidence: float = 0.7,
    project: Optional[str] = None,
    vault_path: Optional[Union[str, Path]] = None,
    project_root: Optional[Union[str, Path]] = None,
    scope: Optional[str] = None,
    project_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Validate, persist and graph one explicitly requested memory.

    ``project`` is a stored identifier. When omitted, the current project's
    directory name is used. ``project_root`` is only used to derive that
    default and is never persisted as a path.
    """
    normalized_type = str(type_).strip()
    normalized_content = str(content).strip()
    if not normalized_type:
        raise ValueError("type_ must not be empty")
    if not normalized_content:
        raise ValueError("content must not be empty")
    if not 0.0 <= confidence <= 1.0:
        raise ValueError("confidence must be between 0.0 and 1.0")

    vault = Path(vault_path).expanduser() if vault_path else default_vault_path()
    resolved_scope, project_label, resolved_project_id = resolve_capture_scope(
        scope=scope,
        project=project or "",
        project_id=project_id or "",
        project_root=project_root,
        registry_path=project_registry_path(vault),
        default_to_project=scope is None,
    )

    validator = MemoryValidator(str(vault))
    candidate, issues, is_new = validator.validate_single_and_append(
        type_=normalized_type,
        content=normalized_content,
        confidence=confidence,
        source="remember",
        scope=resolved_scope,
        project=project_label,
        project_id=resolved_project_id,
        registry_path=str(project_registry_path(vault)),
    )

    if not is_new:
        return {
            "memory_id": candidate.get("memory_id"),
            "status": "duplicate_returned_existing",
            "is_new": False,
            "scope": candidate.get("scope", resolved_scope),
            "project": candidate.get("project", project_label),
            "project_id": candidate.get("project_id", resolved_project_id),
            "issues": [],
        }

    # Keep the graph as a derived projection, exactly like the API path.
    rebuilt_graph = EntityExtractor(str(vault)).build_graph()
    return {
        "memory_id": candidate.memory_id,
        "status": "created",
        "is_new": True,
        "scope": candidate.scope,
        "project": candidate.project,
        "project_id": candidate.project_id,
        "is_approved": candidate.is_approved,
        "quality_score": candidate.quality_score,
        "issues": [issue.description for issue in issues],
        "graph": rebuilt_graph.stats(),
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Capture one memory in Brain-Eleven")
    parser.add_argument("--vault", default=None, help="Brain-Eleven vault path")
    parser.add_argument("--project-root", default=None, help="Current project root used for default project ID")
    parser.add_argument("--project", default=None, help="Display project label; defaults to project directory name")
    parser.add_argument("--project-id", default=None, help="Opaque project namespace ID")
    parser.add_argument("--scope", choices=(GLOBAL_SCOPE, PROJECT_SCOPE), default=None)
    parser.add_argument("--type", dest="type_", help="Memory type: decision, lesson, open_loop, observation")
    parser.add_argument("--content", help="Memory content")
    parser.add_argument("--confidence", type=float, default=0.7)
    parser.add_argument(
        "--check-opt-in",
        action="store_true",
        help="Check the canonical registry policy and exit 0 when capture is allowed",
    )
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    vault = Path(args.vault).expanduser() if args.vault else default_vault_path()
    project_root = args.project_root or str(Path.cwd())

    if args.check_opt_in:
        policy = proactive_capture_policy(project_root=project_root, vault_path=vault)
        print(json.dumps({"opted_in": policy["allowed"], **policy}))
        return 0 if policy["allowed"] else 1

    if args.type_ is None or args.content is None:
        parser.error("--type and --content are required unless --check-opt-in is used")

    result = remember(
        type_=args.type_,
        content=args.content,
        confidence=args.confidence,
        project=args.project,
        project_id=args.project_id,
        scope=args.scope,
        vault_path=vault,
        project_root=project_root,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
