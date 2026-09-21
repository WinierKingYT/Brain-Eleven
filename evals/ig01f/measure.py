"""Run the frozen public IG01-F V1/V2/recency measurement."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import tempfile
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Mapping, Sequence

from evals.baseline import BaselineContextProvider
from evals.compiler_v2_provider import CompilerV2ContextProvider
from evals.contracts import NormalizedEvaluationResult
from evals.ig01c.metrics import evaluate_retrieval_case

from .corpus import DEFAULT_OUTPUT, check_projection
from .provider import RecencyContinuityProvider, _render_item


ROOT = Path(__file__).resolve().parents[2]
PROVIDERS = ("v1", "v2", "recency")
SOURCE_PATHS = (
    ROOT / "evals/ig01f/corpus.py",
    ROOT / "evals/ig01f/provider.py",
    ROOT / "evals/ig01f/measure.py",
    ROOT / "evals/ig01f/public/ig01f-recency-v1/manifest.json",
    ROOT / "evals/ig01f/public/ig01f-recency-v1/dev.jsonl",
    ROOT / "evals/ig01f/public/ig01f-recency-v1/validation.jsonl",
    ROOT / "evals/ig01f/public/ig01f-recency-v1/abstention.jsonl",
)


class MeasurementError(RuntimeError):
    """Raised when frozen measurement inputs or evidence are invalid."""


def _source_git_sha() -> str:
    command = ["git", "log", "-1", "--format=%H", "--", *(str(path.relative_to(ROOT)) for path in SOURCE_PATHS)]
    sha = subprocess.run(command, cwd=ROOT, check=True, capture_output=True, text=True).stdout.strip().lower()
    if len(sha) != 40 or any(char not in "0123456789abcdef" for char in sha):
        raise MeasurementError("measurement source revision is unavailable")
    return sha


def _fingerprint(paths: Sequence[Path] = SOURCE_PATHS) -> str:
    digest = hashlib.sha256()
    for path in sorted(paths, key=lambda item: item.as_posix()):
        relative = path.relative_to(ROOT).as_posix().encode()
        content = path.read_bytes().replace(b"\r\n", b"\n")
        digest.update(len(relative).to_bytes(4, "big"))
        digest.update(relative)
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
    return f"sha256:{digest.hexdigest()}"


def _load(name: str) -> list[dict[str, Any]]:
    if "holdout" in name.casefold() or name not in {"dev", "validation", "abstention"}:
        raise MeasurementError("IG01-F measurement refuses HOLDOUT and unknown splits")
    path = DEFAULT_OUTPUT / f"{name}.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _write_vault(root: Path, row: Mapping[str, Any]) -> None:
    target = root / ".claude" / "validated-memory.json"
    target.parent.mkdir(parents=True)
    target.write_text(json.dumps({
        "schema_version": 2, "revision": 0,
        "updated_at": "2025-01-01T00:00:00Z", "validated_at": "2025-01-01T00:00:00Z",
        "summary": {"source": "ig01f_public_projection"},
        "validated_memory": row["memories"], "rejected_memory": [],
    }, sort_keys=True), encoding="utf-8")


def _bounded(result: NormalizedEvaluationResult) -> NormalizedEvaluationResult:
    estimator = RecencyContinuityProvider().estimator
    selected = []
    rendered = ""
    for item in result.selected_items:
        candidate = rendered + _render_item(item)
        estimate = estimator.estimate(candidate)
        if estimate.count > 1920 or estimate.byte_count > 24_000:
            break
        selected.append(item)
        rendered = candidate
    return NormalizedEvaluationResult(
        task_id=result.task_id, provider_id=result.provider_id, selected_items=tuple(selected),
        source_memory_revision=result.source_memory_revision, project_id=result.project_id,
        retrieval_scope=result.retrieval_scope, capabilities=result.capabilities,
    )


def _select(provider: str, row: Mapping[str, Any]) -> list[str]:
    task = SimpleNamespace(task_id=row["case_id"], project_id=row["project_id"], prompt=row["task_text"])
    implementation = {"v1": BaselineContextProvider, "v2": CompilerV2ContextProvider,
                      "recency": RecencyContinuityProvider}[provider]()
    with tempfile.TemporaryDirectory(prefix="ig01f-") as directory:
        vault = Path(directory) / "vault"
        _write_vault(vault, row)
        result = _bounded(implementation.select(task, vault))
        return [item.id for item in result.selected_items]


def _metric_value(case_result: Mapping[str, Any], name: str) -> float | None:
    row = case_result["metrics"].get(name)
    if not isinstance(row, Mapping) or row.get("not_applicable"):
        return None
    return float(row["value"])


def _summary(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    names = ("precision_at_k", "recall_at_k", "f1", "mrr", "mandatory_recall", "noise_ratio", "context_precision")
    result: dict[str, Any] = {"case_count": len(rows)}
    for name in names:
        values = [value for row in rows if (value := _metric_value(row, name)) is not None]
        result[name] = round(sum(values) / len(values), 6) if values else None
    result["leakage"] = {gate: sum(gate in row["violations"] for row in rows) for gate in
                         ("forbidden_leakage", "wrong_project_leakage", "superseded_leakage", "resolved_leakage")}
    return result


def _group(cases: Sequence[Mapping[str, Any]], evaluated: Mapping[str, Mapping[str, Any]], key: str) -> dict[str, Any]:
    return {value: _summary([evaluated[str(case["case_id"])] for case in cases if str(case[key]) == value])
            for value in sorted({str(case[key]) for case in cases})}


def _paired(left: Mapping[str, Mapping[str, Any]], right: Mapping[str, Mapping[str, Any]]) -> dict[str, int]:
    result = {"wins": 0, "ties": 0, "losses": 0}
    for case_id in sorted(left):
        a = _metric_value(left[case_id], "f1") or 0.0
        b = _metric_value(right[case_id], "f1") or 0.0
        result["wins" if a > b else "losses" if a < b else "ties"] += 1
    return result


def validate_evidence(report: Mapping[str, Any]) -> dict[str, Any]:
    required = {"schema_version", "report_type", "source", "budget", "providers", "paired", "abstention"}
    if set(report) != required or report.get("schema_version") != 1 or report.get("report_type") != "ig01f-naive-baseline-evidence":
        raise MeasurementError("invalid IG01-F evidence envelope")
    source = report.get("source")
    if not isinstance(source, Mapping) or set(source) != {"git_sha", "source_fingerprint", "corpus_version", "splits", "holdout_included"}:
        raise MeasurementError("invalid IG01-F source envelope")
    if source.get("holdout_included") is not False or source.get("splits") != ["dev", "validation"]:
        raise MeasurementError("IG01-F evidence must be DEV+VALIDATION without HOLDOUT")
    if set(report.get("providers", {})) != set(PROVIDERS):
        raise MeasurementError("IG01-F evidence must contain all providers")
    for provider in PROVIDERS:
        provider_report = report["providers"].get(provider)
        if not isinstance(provider_report, Mapping) or set(provider_report) != {"aggregate", "by_phenomenon", "by_language", "case_results"}:
            raise MeasurementError("invalid IG01-F provider evidence")
        if provider == "recency" and any(provider_report["aggregate"]["leakage"].values()):
            raise MeasurementError("recency evidence contains leakage")
    if set(report.get("paired", {})) != {"recency_vs_v1", "recency_vs_v2"}:
        raise MeasurementError("invalid IG01-F paired evidence")
    return dict(report)


def build_evidence() -> dict[str, Any]:
    check_projection()
    cases = _load("dev") + _load("validation")
    abstention = _load("abstention")
    outputs: dict[str, dict[str, list[str]]] = {provider: {} for provider in PROVIDERS}
    evaluated: dict[str, dict[str, dict[str, Any]]] = {provider: {} for provider in PROVIDERS}
    for provider in PROVIDERS:
        for case in cases:
            case_id = str(case["case_id"])
            selected = _select(provider, case)
            outputs[provider][case_id] = selected
            evaluated[provider][case_id] = evaluate_retrieval_case(case, selected, k=5)
    provider_reports = {provider: {
        "aggregate": _summary(list(evaluated[provider].values())),
        "by_phenomenon": _group(cases, evaluated[provider], "category"),
        "by_language": _group(cases, evaluated[provider], "language"),
        "case_results": [{"case_id": case_id, "selected_ids": outputs[provider][case_id],
                          "metrics": evaluated[provider][case_id]["metrics"],
                          "violations": evaluated[provider][case_id]["violations"]}
                         for case_id in sorted(outputs[provider])],
    } for provider in PROVIDERS}
    abstention_report = {provider: {"case_count": len(abstention),
                                    "empty_selection_count": sum(not _select(provider, case) for case in abstention)}
                         for provider in PROVIDERS}
    report = {
        "schema_version": 1, "report_type": "ig01f-naive-baseline-evidence",
        "source": {"git_sha": _source_git_sha(), "source_fingerprint": _fingerprint(),
                   "corpus_version": "ig01f-recency-v1", "splits": ["dev", "validation"],
                   "holdout_included": False},
        "budget": {"max_context_tokens": 2048, "minimum_headroom_tokens": 128,
                   "usable_tokens": 1920, "hard_byte_limit": 24_000, "estimator": "utf8-conservative-v1"},
        "providers": provider_reports,
        "paired": {"recency_vs_v1": _paired(evaluated["recency"], evaluated["v1"]),
                   "recency_vs_v2": _paired(evaluated["recency"], evaluated["v2"])},
        "abstention": abstention_report,
    }
    return validate_evidence(report)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    payload = json.dumps(build_evidence(), sort_keys=True, indent=2) + "\n"
    if args.check:
        if not args.output.is_file() or args.output.read_text(encoding="utf-8") != payload:
            raise MeasurementError("committed IG01-F evidence differs from frozen regeneration")
    else:
        args.output.write_text(payload, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
