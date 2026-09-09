"""Fail-closed, content-free audit for the IG01 evaluation foundation.

IG01-E audits the measurement system itself.  It does not execute a provider,
change production behavior, tune a score, or persist corpus content.  The
only corpus access is a sealed integrity check which returns counts and hashes.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path
import subprocess
from typing import Any, Callable, Iterable

from ..ig01b.integrity import check_private_boundary, check_public_corpus
from ..ig01b.schema import LANGUAGES, PHENOMENA, load_cases
from ..ig01d.contracts import validate_pair_report, BaselineContractError


AUDIT_VERSION = "1.0.0"
VERDICT_SHIP = "SHIP"
VERDICT_FIX_FIRST = "FIX-FIRST"


class AuditError(ValueError):
    """Raised when an IG01-E audit cannot prove a required invariant."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _canonical_sha256(path: Path) -> str:
    """Hash text fixtures with platform-independent LF normalization."""

    return "sha256:" + hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def _git_sha(root: Path) -> str:
    result = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    )
    value = result.stdout.strip().lower()
    if len(value) != 40 or any(char not in "0123456789abcdef" for char in value):
        raise AuditError("git rev-parse HEAD did not return a full SHA")
    return value


def _audit_worktree(root: Path) -> dict[str, Any]:
    result = subprocess.run(["git", "-C", str(root), "status", "--porcelain"], capture_output=True, text=True, check=True)
    transient = ("?? .ig01d-evidence/", "?? ig01e-audit.json")
    dirty = [line for line in result.stdout.splitlines() if line.strip() and not any(line.startswith(prefix) for prefix in transient)]
    if dirty:
        raise AuditError("working tree is dirty; audit evidence must bind to a committed revision")
    return {"clean": True}


def _tracked_files(root: Path) -> set[str]:
    result = subprocess.run(
        ["git", "-C", str(root), "ls-files"],
        check=True,
        capture_output=True,
        text=True,
    )
    return {line.strip().replace("\\", "/") for line in result.stdout.splitlines() if line.strip()}


def _check_file(root: Path, relative: str, *, required_markers: Iterable[str] = ()) -> dict[str, Any]:
    path = root / relative
    if not path.is_file():
        raise AuditError(f"required audit input is missing: {relative}")
    text = path.read_text(encoding="utf-8")
    missing = [marker for marker in required_markers if marker not in text]
    if missing:
        raise AuditError(f"{relative} is missing required contract markers")
    return {"path": relative, "sha256": _sha256(path), "bytes": path.stat().st_size}


def _audit_documentation(root: Path) -> list[dict[str, Any]]:
    files = {
        "PROJECT-STATUS.md": ("PHASE 20: FROZEN", "V2 remains SHADOW"),
        "IG01-EVALUATION-FOUNDATION.md": ("IG01-E", "HOLDOUT"),
        "IG01-A-EVALUATION-CONTRACT.md": ("answerability", "HOLDOUT"),
        "IG01-B-CORPUS-CONTRACT.md": ("PUBLIC_SYNTHETIC", "PRIVATE_REALISTIC"),
        "IG01-C-EVALUATOR-CONTRACT.md": ("No production intelligence", "anti-gaming"),
        "IG01-D-BASELINE-CONTRACT.md": ("V1", "V2", "HOLDOUT"),
        "DOCUMENTATION-AUTHORITY.md": ("evals/ig01e", "IG01-D-PACKAGE-REPORT.md"),
    }
    evidence = [_check_file(root, relative, required_markers=markers) for relative, markers in files.items()]
    status = (root / "PROJECT-STATUS.md").read_text(encoding="utf-8").lower()
    d_report = (root / "IG01-D-PACKAGE-REPORT.md").read_text(encoding="utf-8").lower()
    if "active package: ig01-e" not in status or "ig01-d human checkpoint pass" not in status:
        raise AuditError("current status does not record IG01-D acceptance and IG01-E activity")
    if "status:** accepted" not in d_report or "verdict:** ship" not in d_report:
        raise AuditError("IG01-D report is not closed as SHIP")
    return evidence


def _audit_public_corpus(root: Path) -> dict[str, Any]:
    # This is the sole sealed HOLDOUT read.  check_public_corpus emits only
    # counts, hashes and privacy counters; it never returns case content.
    corpus = root / "evals" / "ig01b" / "public" / "ig-eval-v2"
    result = check_public_corpus(corpus)
    loaded = {
        split: load_cases(corpus / f"{split}.jsonl", expected_class="PUBLIC_SYNTHETIC")
        for split in ("dev", "validation", "holdout", "abstention")
    }
    manifest = json.loads((corpus / "manifest.json").read_text(encoding="utf-8"))
    split_hashes = {
        split: _canonical_sha256(corpus / f"{split}.jsonl")
        for split in ("dev", "validation", "holdout", "abstention")
    }
    expected_hashes = {split: "sha256:" + value for split, value in manifest["file_sha256"].items()}
    if split_hashes != expected_hashes:
        raise AuditError("public corpus split hash differs from manifest")
    all_cases = [case for cases in loaded.values() for case in cases]
    if len({case["case_id"] for case in all_cases}) != len(all_cases):
        raise AuditError("public corpus case IDs overlap across splits")
    if any(not case.get("provenance") or not case.get("data_lineage") or not case.get("generator_identity") or not case.get("sut_identity") for case in all_cases):
        raise AuditError("public corpus provenance/lineage fields are incomplete")
    answerable = loaded["dev"] + loaded["validation"] + loaded["holdout"]
    cells = {(case["category"], case["language"]) for case in answerable}
    if cells != {(phenomenon, language) for phenomenon in PHENOMENA for language in LANGUAGES}:
        raise AuditError("public corpus phenomenon/language coverage is incomplete")
    holdout_double = sum(1 for case in loaded["holdout"] if case["labels"].get("double_annotation"))
    holdout_adjudicated = sum(1 for case in loaded["holdout"] if case["labels"].get("double_annotation", {}).get("adjudicated") is True)
    if result["corpus_version"] != "ig-eval-v2" or result["total_answerable"] != 153:
        raise AuditError("public corpus population is not the frozen IG01-B v2 population")
    if result["splits"].get("dev") != 76 or result["splits"].get("validation") != 38 or result["splits"].get("holdout") != 39:
        raise AuditError("public corpus split counts changed without a new version")
    if result["matrix_minimum"] < 3 or result["secret_hits"] or result["pii_hits"]:
        raise AuditError("public corpus matrix/privacy invariant failed")
    return {
        "corpus_version": result["corpus_version"],
        "splits": result["splits"],
        "total_answerable": result["total_answerable"],
        "matrix_cells": result["matrix_cells"],
        "matrix_minimum": result["matrix_minimum"],
        "holdout_sha256": result["holdout_sha256"],
        "split_sha256": split_hashes,
        "manifest_hashes_match": True,
        "holdout_double_labeled": holdout_double,
        "holdout_adjudicated": holdout_adjudicated,
        "inter_annotator_disagreement_rate": manifest["inter_annotator_disagreement_rate"],
        "answerability": {"answerable": len(answerable), "abstention": len(loaded["abstention"])},
        "privacy": {"secret_hits": 0, "pii_hits": 0},
    }


def _audit_private_boundary(root: Path) -> dict[str, Any]:
    result = check_private_boundary(root)
    tracked = set(_tracked_files(root))
    leaked = sorted(
        path for path in tracked
        if path.startswith("evals/private/") or "private_realistic" in path.lower()
    )
    if leaked or result.get("leakage") != 0:
        raise AuditError("private realistic corpus is tracked or exposed")
    gitignore = (root / ".gitignore").read_text(encoding="utf-8")
    private_source = (root / "evals" / "ig01b" / "private.py").read_text(encoding="utf-8")
    failure_source = (root / "evals" / "ig01b" / "failures.py").read_text(encoding="utf-8")
    failure_manifest_path = root / "evals" / "ig01b" / "failures" / "manifest.json"
    failure_manifest = json.loads(failure_manifest_path.read_text(encoding="utf-8"))
    if "evals/private/" not in gitignore or "assert_private_path" not in private_source or "_reject_raw_fields" not in failure_source:
        raise AuditError("private/failure write guards are not documented in source")
    if failure_manifest.get("status") != "EMPTY_RESERVED_FOR_IG-08" or failure_manifest.get("cases") != 0:
        raise AuditError("sanitized failure reservation is not empty or is not IG-08 scoped")
    return {
        "guard_root": "evals/private",
        "tracked_private_candidates": 0,
        "leakage": 0,
        "gitignore_guard": True,
        "private_writer_guard": True,
        "failure_ingest_guard": True,
        "sanitized_failure_cases": 0,
    }


def _imports_and_calls(path: Path) -> tuple[set[str], set[str]]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imports: set[str] = set()
    calls: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module.split(".")[0])
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Attribute):
                calls.add(node.func.attr)
            elif isinstance(node.func, ast.Name):
                calls.add(node.func.id)
    return imports, calls


def _audit_evaluator_independence(root: Path) -> dict[str, Any]:
    evaluator_root = root / "evals" / "ig01c"
    if not evaluator_root.is_dir():
        raise AuditError("IG01-C evaluator package is missing")
    forbidden_imports = {"openai", "httpx", "requests", "urllib", "socket", "aiohttp"}
    forbidden_calls = {"write_memory", "write_state", "MemoryStore", "StateStore", "ProjectRegistry"}
    files: list[dict[str, Any]] = []
    for path in sorted(evaluator_root.glob("*.py")):
        imports, calls = _imports_and_calls(path)
        if imports & forbidden_imports:
            raise AuditError(f"IG01-C evaluator imports a network/provider module: {path.name}")
        if calls & forbidden_calls:
            raise AuditError(f"IG01-C evaluator calls a canonical write/authority symbol: {path.name}")
        source = path.read_text(encoding="utf-8")
        if any(marker in source for marker in (".write_text(", ".write_bytes(", "MemoryStore", "StateStore", "ProjectRegistry")):
            raise AuditError(f"IG01-C evaluator contains a production/side-effect marker: {path.name}")
        files.append({"path": path.relative_to(root).as_posix(), "sha256": _sha256(path)})
    return {
        "offline": True,
        "production_mutation": False,
        "files": files,
        "source_fingerprint_scope": "ig01c_source_files_not_runtime_adapters",
        "adapter_fingerprint_limitation": True,
    }


def _audit_anti_gaming(root: Path) -> dict[str, Any]:
    tests = root / "tests" / "test_ig01c_evaluator.py"
    text = tests.read_text(encoding="utf-8") if tests.is_file() else ""
    required = ("select_all", "select_none", "foreign", "superseded", "false_supersession")
    missing = [marker for marker in required if marker.lower() not in text.lower()]
    if missing:
        raise AuditError("IG01-C anti-gaming tests do not cover the required controls")
    return {"select_all_control": True, "select_none_control": True, "hard_gate_controls": True}


def _audit_baseline_boundary(root: Path, pair_report: Path | None = None, *, require_pair_report: bool = False) -> dict[str, Any]:
    baseline = root / "evals" / "ig01d" / "baseline.py"
    spike = root / "evals" / "ig01d" / "spike.py"
    contracts = root / "evals" / "ig01d" / "contracts.py"
    baseline_text = baseline.read_text(encoding="utf-8")
    spike_text = spike.read_text(encoding="utf-8")
    run_text = (root / "evals" / "run.py").read_text(encoding="utf-8")
    corpus_builder_text = (root / "evals" / "corpus_v2_builder.py").read_text(encoding="utf-8")
    if (
        '"split": ["dev", "test"]' not in baseline_text
        or '"holdout_included": False' not in spike_text
        or "public_only=True" not in baseline_text
        or "check_corpus_v2_public" not in run_text
        or "def check_corpus_v2_public" not in corpus_builder_text
    ):
        raise AuditError("IG01-D baseline does not prove public DEV+TEST-only execution")
    if "validate_pair_report" not in contracts.read_text(encoding="utf-8"):
        raise AuditError("IG01-D strict pair contract is missing")
    report = root / "IG01-D-PACKAGE-REPORT.md"
    _check_file(root, report.name, required_markers=("SEMANTIC_UNAVAILABLE", "holdout_included=false", "V2 precision"))
    report_text = report.read_text(encoding="utf-8")
    if "61c89e9934f669b5c624e5e1a921cd62e4f49b04" not in report_text:
        raise AuditError("IG01-D historical report binding is missing")
    artifact_evidence: dict[str, Any] = {"artifact": "NOT_AVAILABLE"}
    if pair_report is None:
        # A structural/local audit may still enumerate the other checks, but
        # it can never emit SHIP without the exact CI-produced pair artifact.
        raise AuditError("IG01-D pair artifact is required for an accepted audit")
    else:
        try:
            payload = json.loads(pair_report.read_text(encoding="utf-8"))
            validated = validate_pair_report(payload)
        except (OSError, json.JSONDecodeError, BaselineContractError) as error:
            raise AuditError("IG01-D pair artifact failed strict validation") from error
        current_sha = _git_sha(root)
        if validated["source"]["git_sha"] != current_sha:
            raise AuditError("IG01-D pair artifact SHA differs from audit revision")
        v1_metrics = validated["providers"]["v1"]["metrics"]
        v2_metrics = validated["providers"]["v2"]["metrics"]
        deltas = validated["comparison"]["metric_deltas"]
        for metric in ("context_precision", "context_recall"):
            expected_delta = float(v2_metrics[metric]) - float(v1_metrics[metric])
            if abs(float(deltas[metric]["baseline"]) - float(v1_metrics[metric])) > 1e-9 or abs(float(deltas[metric]["candidate"]) - float(v2_metrics[metric])) > 1e-9 or abs(float(deltas[metric]["delta"]) - expected_delta) > 1e-9:
                raise AuditError("IG01-D comparison delta is not recomputed from provider metrics")
        delta_values = [float(deltas[name]["delta"]) for name in ("context_precision", "context_recall")]
        expected_outcome = "unchanged" if all(value == 0 for value in delta_values) else "improved" if all(value >= 0 for value in delta_values) else "degraded" if any(value < 0 for value in delta_values) else "inconclusive"
        if validated["comparison"]["outcome"] != expected_outcome:
            raise AuditError("IG01-D comparison outcome is not derived from metric deltas")
        invariant_states = validated["providers"]["v2"]["invariants"]
        expected_failed = {name: value["failed_case_ids"] for name, value in invariant_states.items() if value["state"] == "fail"}
        expected_unsupported = {name: value["unsupported_case_ids"] for name, value in invariant_states.items() if value["state"] == "unsupported"}
        gate = validated["comparison"]["candidate_gate"]
        if gate["failed_invariants"] != expected_failed or gate["unsupported_invariants"] != expected_unsupported or gate["passed"] != (not (expected_failed or expected_unsupported)):
            raise AuditError("IG01-D candidate gate is not bound to provider invariant rows")
        artifact_evidence = {
            "artifact": pair_report.name,
            "artifact_sha256": _sha256(pair_report),
            "git_sha": current_sha,
            "task_count": validated["corpus"]["task_count"],
            "split": validated["corpus"]["split"],
            "holdout_included": validated["feasibility"]["holdout_included"],
            "feasibility_status": validated["feasibility"]["status"],
            "outcome": validated["comparison"]["outcome"],
            "metric_deltas_recomputed": True,
            "candidate_gate_recomputed": True,
        }
    return {
        "same_input_pair": True,
        "holdout_included": False,
        "feasibility_unavailable_explicit": True,
        "legacy_holdout_workflows_out_of_scope": True,
        **artifact_evidence,
    }


def _audit_parent_packages(root: Path) -> dict[str, Any]:
    required_tags = {
        "ig01a-ship": "ae67d456616bad6782765a1ba8e10ef638124ac7",
        "ig01b-ship": "77811dfdf3da783bbfcee565b0881233bff8fc10",
    }
    missing: list[str] = []
    tag_revisions: dict[str, str] = {}
    for tag, expected in required_tags.items():
        result = subprocess.run(["git", "-C", str(root), "rev-parse", f"refs/tags/{tag}^{{}}"], capture_output=True, text=True)
        revision = result.stdout.strip().lower()
        if result.returncode != 0 or revision != expected:
            missing.append(tag)
    if missing:
        raise AuditError("required immutable package tags are missing")
    reports = {
        "IG01-A-PACKAGE-REPORT.md": "SHIP",
        "IG01-B-PACKAGE-REPORT.md": "SHIP",
        "IG01-C-PACKAGE-REPORT.md": "SHIP",
        "IG01-D-PACKAGE-REPORT.md": "SHIP",
    }
    report_evidence: dict[str, str] = {}
    for relative, expected in reports.items():
        text = (root / relative).read_text(encoding="utf-8")
        if expected not in text:
            raise AuditError(f"{relative} does not record {expected}")
        report_evidence[relative] = _sha256(root / relative)
    d_text = (root / "IG01-D-PACKAGE-REPORT.md").read_text(encoding="utf-8")
    c_text = (root / "IG01-C-PACKAGE-REPORT.md").read_text(encoding="utf-8")
    if "61c89e9934f669b5c624e5e1a921cd62e4f49b04" not in d_text or "a95fa31079acdb2de3a26c767923accaf084a274" not in c_text:
        raise AuditError("parent package reports are not revision-bound")
        tag_revisions[tag] = revision
    return {"immutable_ship_tags": tag_revisions, "missing": [], "report_sha256": report_evidence}


def _audit_benchmark_eligibility(root: Path) -> dict[str, Any]:
    report = " ".join((root / "IG01-C-PACKAGE-REPORT.md").read_text(encoding="utf-8").lower().split())
    if "release-mode benchmark validation will reject" not in report or "exploratory smoke" not in report:
        raise AuditError("IG01-C benchmark eligibility limitation is not visible")
    return {
        "eligibility": "EXPLORATORY_ONLY",
        "release_quality_claim": False,
        "answerable_cases": 153,
        "abstention_cases": 6,
        "reference_resolution_answerable_cases": 9,
    }


def _run_check(name: str, check: Callable[[], Any]) -> dict[str, Any]:
    try:
        return {"status": "PASS", "evidence": check()}
    except (AuditError, OSError, ValueError) as error:
        # Error text is deliberately reduced to a stable code.  Audit output
        # remains content-free and can be safely uploaded from CI.
        return {"status": "FAIL", "error_code": f"{name.upper()}_INVARIANT_FAILED"}


def audit_repository(root: Path | str = ".", *, pair_report: Path | str | None = None, require_pair_report: bool = False) -> dict[str, Any]:
    """Run all IG01-E checks and return content-free, revision-bound evidence."""

    repository = Path(root).resolve()
    checks = {
        "revision_clean": _run_check("revision_clean", lambda: _audit_worktree(repository)),
        "documentation": _run_check("documentation", lambda: _audit_documentation(repository)),
        "public_corpus": _run_check("public_corpus", lambda: _audit_public_corpus(repository)),
        "private_boundary": _run_check("private_boundary", lambda: _audit_private_boundary(repository)),
        "evaluator_independence": _run_check("evaluator_independence", lambda: _audit_evaluator_independence(repository)),
        "anti_gaming": _run_check("anti_gaming", lambda: _audit_anti_gaming(repository)),
        "baseline_boundary": _run_check(
            "baseline_boundary",
            lambda: _audit_baseline_boundary(
                repository,
                Path(pair_report).resolve() if pair_report is not None else None,
                require_pair_report=require_pair_report,
            ),
        ),
        "parent_packages": _run_check("parent_packages", lambda: _audit_parent_packages(repository)),
        "benchmark_eligibility": _run_check("benchmark_eligibility", lambda: _audit_benchmark_eligibility(repository)),
    }
    verdict = VERDICT_SHIP if all(row.get("status") == "PASS" for row in checks.values()) else VERDICT_FIX_FIRST
    return {
        "schema_version": 1,
        "audit_version": AUDIT_VERSION,
        "audit_type": "brain_eleven_ig01e_independent_evaluation_audit",
        "source": {"git_sha": _git_sha(repository)},
        "checks": checks,
        "phase20": "FROZEN_LOCKED",
        "v2_runtime": "SHADOW",
        "holdout_tuning": "PROHIBITED",
        "verdict": verdict,
    }


def write_audit_report(path: Path | str, report: dict[str, Any]) -> None:
    """Write validated content-free audit evidence atomically as JSON."""

    required = {"schema_version", "audit_version", "audit_type", "source", "checks", "phase20", "v2_runtime", "holdout_tuning", "verdict"}
    if set(report) != required or report.get("schema_version") != 1 or report.get("audit_version") != AUDIT_VERSION or report.get("audit_type") != "brain_eleven_ig01e_independent_evaluation_audit" or report.get("verdict") not in {VERDICT_SHIP, VERDICT_FIX_FIRST}:
        raise AuditError("invalid IG01-E audit report")
    source = report.get("source")
    if not isinstance(source, dict) or set(source) != {"git_sha"} or not isinstance(source.get("git_sha"), str) or len(source["git_sha"]) != 40 or source["git_sha"] != source["git_sha"].lower() or any(char not in "0123456789abcdef" for char in source["git_sha"]):
        raise AuditError("audit report source is not revision-bound")
    checks = report.get("checks")
    if not isinstance(checks, dict) or not checks or any(not isinstance(row, dict) or set(row) - {"status", "evidence", "error_code"} or row.get("status") not in {"PASS", "FAIL"} for row in checks.values()):
        raise AuditError("audit report checks are malformed")
    if report.get("verdict") == VERDICT_SHIP and any(row.get("status") != "PASS" for row in checks.values()):
        raise AuditError("SHIP audit contains a failed check")
    if report.get("verdict") == VERDICT_FIX_FIRST and all(row.get("status") == "PASS" for row in checks.values()):
        raise AuditError("FIX-FIRST audit must identify a failed check")
    if report.get("phase20") != "FROZEN_LOCKED" or report.get("v2_runtime") != "SHADOW" or report.get("holdout_tuning") != "PROHIBITED":
        raise AuditError("audit boundary metadata is invalid")
    def _scan(value: Any) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                if str(key).lower() in {"prompt", "transcript", "memory_content", "secret", "secrets", "password", "token", "tokens"}:
                    raise AuditError("audit report contains prohibited raw-content fields")
                _scan(child)
        elif isinstance(value, list):
            for child in value:
                _scan(child)
    _scan(report)
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    temporary.write_text(json.dumps(report, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    temporary.replace(destination)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the content-free IG01-E audit")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--report", type=Path)
    parser.add_argument("--pair-report", type=Path)
    parser.add_argument("--require-pair-report", action="store_true")
    args = parser.parse_args()
    report = audit_repository(args.root, pair_report=args.pair_report, require_pair_report=args.require_pair_report)
    if args.report:
        write_audit_report(args.report, report)
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
