"""Repository-wide pytest compatibility aliases for legacy script imports.

Production code imports the installable ``scripts`` package. Existing tests
also exercise the historical bare module names; aliasing those names here
keeps their identity/parity assertions intact without changing ``sys.path``.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path


_ROOT = Path(__file__).parent


def _alias_package_module(name: str) -> None:
    if not (_ROOT / "scripts" / f"{name}.py").exists():
        return
    module = importlib.import_module(f"scripts.{name}")
    sys.modules.setdefault(name, module)


for _module_name in (
    "anomaly_detector",
    "cache_manager",
    "chat_interface",
    "context_engine_foundation_evidence",
    "entity_extractor",
    "graduation_evidence",
    "knowledge_graph",
    "logging_config",
    "memory_backup",
    "memory_provenance",
    "memory_store",
    "project_registry",
    "phase15_evidence",
    "phase16_evidence",
    "phase17_evidence",
    "phase18_evidence",
    "phase19_evidence",
    "post_session_maintenance",
    "remember",
    "remember_opt_in",
    "report_bandit_findings",
    "report_junit_failures",
    "report_trivy_findings",
    "session_pipeline",
    "state_store",
    "summarizer",
    "task_model",
    "task_state_context",
):
    _alias_package_module(_module_name)
