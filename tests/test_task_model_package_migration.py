"""Gate evidence for the IG-07 Slice 2E task-model inversion."""

from __future__ import annotations

import ast
import importlib
import json
import subprocess
import sys
from pathlib import Path

from evals.task_state_eval import run_task_state_evaluation


ROOT = Path(__file__).resolve().parents[1]
BASELINE_DIR = ROOT / "evals" / "reports" / "ig07-slice2e"


IDENTITY_NAMES = (
    "ProjectRegistry",
    "ProjectRegistryError",
    "TASK_SCHEMA_VERSION",
    "TASK_ID_PREFIX",
    "TASK_LIFECYCLES",
    "PROJECT_RESOLUTION_STATUSES",
    "INTENTS",
    "OPERATIONS",
    "RISK_LEVELS",
    "REQUESTED_OUTPUTS",
    "EVIDENCE_SOURCES",
    "MAX_REQUEST_CHARS",
    "TaskValidationError",
    "TaskProjectResolutionError",
    "TaskAnalyzer",
    "Evidence",
    "ProjectResolution",
    "TaskEnvelope",
    "utc_now",
    "new_task_id",
    "resolve_project",
    "validate_task",
    "render_task_json",
)


def test_package_adapter_and_bare_task_model_share_all_contract_objects():
    canonical = importlib.import_module("brain_eleven.runtime.task")
    adapter = importlib.import_module("scripts.task_model")
    bare = importlib.import_module("task_model")

    for name in IDENTITY_NAMES:
        assert getattr(canonical, name) is getattr(adapter, name), name
        assert getattr(adapter, name) is getattr(bare, name), name

    assert adapter.TaskEnvelope.from_dict.__func__ is canonical.TaskEnvelope.from_dict.__func__


def test_task_state_context_consumes_the_canonical_task_objects():
    canonical = importlib.import_module("brain_eleven.runtime.task")
    context = importlib.import_module("scripts.task_state_context")

    assert context.TaskAnalyzer is canonical.TaskAnalyzer
    assert context.TaskEnvelope is canonical.TaskEnvelope
    assert context.TaskValidationError is canonical.TaskValidationError
    assert context.TaskProjectResolutionError is canonical.TaskProjectResolutionError


def test_task_model_adapter_contains_no_second_implementation_or_write_path():
    path = ROOT / "scripts" / "task_model.py"
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    definitions = {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
    }

    assert definitions == {"_load_canonical"}
    assert "MemoryStore" not in source
    assert "StateStore" not in source
    assert "json.dump" not in source
    assert "open(" not in source


def test_canonical_task_module_uses_package_registry_surface():
    source = (ROOT / "brain_eleven" / "runtime" / "task.py").read_text(encoding="utf-8")

    assert "from brain_eleven.projects.registry import" in source
    assert "from scripts.task_model import" not in source


def test_task_state_context_has_no_worktree_diff():
    result = subprocess.run(
        ["git", "diff", "--quiet", "--", "scripts/task_state_context.py"],
        cwd=ROOT,
        check=False,
    )
    assert result.returncode == 0


def test_public_and_holdout_evaluations_match_immutable_baselines():
    for suite in ("smoke", "public", "holdout"):
        before = json.loads((BASELINE_DIR / f"before-{suite}.json").read_text(encoding="utf-8"))
        after = run_task_state_evaluation(suite=suite)
        assert after == before, suite


def test_direct_adapter_and_package_cli_have_the_same_contract(tmp_path):
    request = "Phase 17 planını hazırla."
    common = [
        "analyze",
        "--vault",
        str(tmp_path / "vault"),
        "--project-root",
        str(tmp_path / "unknown"),
        "--request",
        request,
        "--json",
    ]
    adapter = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "task_model.py"), *common],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    package = subprocess.run(
        [sys.executable, "-m", "brain_eleven.runtime.task", *common],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    adapter_payload = json.loads(adapter.stdout)
    package_payload = json.loads(package.stdout)
    for payload in (adapter_payload, package_payload):
        payload.pop("task_id", None)
        payload.pop("created_at", None)
    assert adapter_payload == package_payload
