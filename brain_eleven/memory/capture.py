"""Canonical manual-memory capture orchestration.

The legacy ``scripts/remember.py`` entrypoint is a compatibility adapter.  The
validator remains the canonical validation/write authority for this bounded
migration; this module deliberately does not duplicate its transaction logic.
The existing capture-safety policy is loaded through the shared legacy loader
so package and historical imports keep the same object identity.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from brain_eleven._legacy import load_legacy_module
from brain_eleven.extraction import EntityExtractor
from brain_eleven.projects.registry import ProjectRegistry, registry_path as project_registry_path

from .scope import GLOBAL_SCOPE, PROJECT_SCOPE, project_identity, resolve_capture_scope


_capture_safety = load_legacy_module("capture_safety", "capture_safety.py")
_memory_validator = load_legacy_module("memory_validator", "memory-validator.py")

evaluate_capture = _capture_safety.evaluate_capture
require_safe_capture = _capture_safety.require_safe_capture
CaptureSafetyError = _capture_safety.CaptureSafetyError
CaptureSafetyResult = _capture_safety.CaptureSafetyResult
MemoryValidator = _memory_validator.MemoryValidator

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_VAULT = REPO_ROOT


def _configure_utf8_output() -> None:
    """Keep CLI diagnostics usable on terminals with legacy encodings."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")


def default_vault_path() -> Path:
    """Return the configured vault, defaulting to the repository root."""
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
    return ProjectRegistry(vault).proactive_capture_policy(
        project_root or Path.cwd()
    )["allowed"]


def proactive_capture_policy(
    project_root: Optional[Union[str, Path]] = None,
    vault_path: Optional[Union[str, Path]] = None,
) -> Dict[str, Any]:
    """Expose registry policy without leaking a filesystem root."""
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

    Manual capture is explicit and therefore does not call the proactive
    opt-in gate.  Persistence remains inside ``MemoryValidator``'s
    ``MemoryStore.transact`` boundary.
    """
    normalized_type = str(type_).strip()
    normalized_content = str(content).strip()
    if not normalized_type:
        raise ValueError("type_ must not be empty")
    if not normalized_content:
        raise ValueError("content must not be empty")
    if not 0.0 <= confidence <= 1.0:
        raise ValueError("confidence must be between 0.0 and 1.0")

    safety = evaluate_capture(normalized_content)
    if not safety.accepted:
        return safety.to_dict()

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

    # The graph is a derived projection; canonical memory remains validator-owned.
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
    _configure_utf8_output()
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
    return 0 if result.get("accepted", True) else 2


__all__ = [
    "GLOBAL_SCOPE",
    "PROJECT_SCOPE",
    "DEFAULT_VAULT",
    "MemoryValidator",
    "EntityExtractor",
    "CaptureSafetyError",
    "CaptureSafetyResult",
    "evaluate_capture",
    "require_safe_capture",
    "default_vault_path",
    "default_project_id",
    "is_project_opted_in",
    "proactive_capture_policy",
    "remember",
    "main",
]


if __name__ == "__main__":
    raise SystemExit(main())
