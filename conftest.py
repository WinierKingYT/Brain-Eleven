"""Repository-wide pytest compatibility aliases for legacy script imports.

Production code imports the installable ``scripts`` package. Existing tests
also exercise the historical bare module names; aliasing those names here
keeps their identity/parity assertions intact without changing ``sys.path``.
"""

from __future__ import annotations

import importlib
import importlib.util
import sys
from pathlib import Path


_ROOT = Path(__file__).parent


def _alias_package_module(name: str) -> None:
    module = importlib.import_module(f"scripts.{name}")
    sys.modules.setdefault(name, module)


def _alias_legacy_script(name: str, filename: str) -> None:
    if name in sys.modules:
        return
    script_path = _ROOT / "scripts" / filename
    specification = importlib.util.spec_from_file_location(name, script_path)
    if specification is None or specification.loader is None:
        raise ImportError(f"Cannot load legacy test module: {filename}")
    module = importlib.util.module_from_spec(specification)
    sys.modules[name] = module
    try:
        specification.loader.exec_module(module)
    except Exception:
        sys.modules.pop(name, None)
        raise


for _module_name in (
    "capture_event",
    "capture_queue",
    "capture_safety",
    "anomaly_detector",
    "cache_manager",
    "chat_interface",
    "context_engine_foundation_evidence",
    "entity_extractor",
    "evidence",
    "extraction",
    "graduation_evidence",
    "knowledge_graph",
    "memory_backup",
    "memory_provenance",
    "memory_scope",
    "memory_store",
    "memory_store_lock",
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
    "state_boundary",
    "state_resolver",
    "state_store",
    "summarizer",
    "task_model",
    "task_state_context",
):
    _alias_package_module(_module_name)

for _module_name, _filename in {
    "memory_compiler": "memory-compiler.py",
    "memory_lifecycle": "memory-lifecycle.py",
    "memory_retriever": "memory-retriever.py",
    "memory_validator": "memory-validator.py",
    "hybrid_search": "hybrid-search.py",
    "ml_ranker": "ml-ranker.py",
}.items():
    _alias_legacy_script(_module_name, _filename)
