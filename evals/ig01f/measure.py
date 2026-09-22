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
from evals.ig01c.engine import evaluate_corpus, validate_report as validate_ig01c_report

from .corpus import DEFAULT_OUTPUT, check_projection
from .provider import RecencyContinuityProvider, _render_item


ROOT = Path(__file__).resolve().parents[2]
PROVIDERS = ("v1", "v2", "recency")
SUMMARY_METRICS = (
    "precision_at_k", "recall_at_k", "f1", "mrr", "mandatory_recall",
    "noise_ratio", "token_waste", "context_precision",
)
LEAKAGE_GATES = (
    "forbidden_leakage", "wrong_project_leakage", "superseded_leakage", "resolved_leakage",
)
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
    result: dict[str, Any] = {"case_count": len(rows)}
    for name in SUMMARY_METRICS:
        values = [value for row in rows if (value := _metric_value(row, name)) is not None]
        result[name] = round(sum(values) / len(values), 6) if values else None
    result["leakage"] = {gate: sum(gate in row["violations"] for row in rows) for gate in LEAKAGE_GATES}
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


def _closed_mapping(value: object, keys: set[str], label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != keys:
        raise MeasurementError(f"invalid IG01-F {label}")
    return value


def _non_negative_int(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise MeasurementError(f"invalid IG01-F {label}")
    return value


def _validate_summary(value: object, label: str) -> Mapping[str, Any]:
    summary = _closed_mapping(
        value,
        {"case_count", *SUMMARY_METRICS, "leakage"},
        f"{label} summary",
    )
    case_count = _non_negative_int(summary["case_count"], f"{label} case_count")
    for metric in SUMMARY_METRICS:
        number = summary[metric]
        if number is None:
            continue
        if isinstance(number, bool) or not isinstance(number, (int, float)) or not 0.0 <= float(number) <= 1.0:
            raise MeasurementError(f"invalid IG01-F {label} metric {metric}")
    leakage = _closed_mapping(summary["leakage"], set(LEAKAGE_GATES), f"{label} leakage")
    for gate, count in leakage.items():
        if _non_negative_int(count, f"{label} {gate}") > case_count:
            raise MeasurementError(f"invalid IG01-F {label} leakage count")
    return summary


def validate_evidence(
    report: Mapping[str, Any], *, source_bound: bool = True, _verify_regeneration: bool = True
) -> dict[str, Any]:
    required = {"schema_version", "report_type", "source", "budget", "providers", "paired", "abstention"}
    if set(report) != required or report.get("schema_version") != 1 or report.get("report_type") != "ig01f-naive-baseline-evidence":
        raise MeasurementError("invalid IG01-F evidence envelope")
    source = report.get("source")
    if not isinstance(source, Mapping) or set(source) != {"git_sha", "source_fingerprint", "corpus_version", "splits", "holdout_included"}:
        raise MeasurementError("invalid IG01-F source envelope")
    if source.get("holdout_included") is not False or source.get("splits") != ["dev", "validation"]:
        raise MeasurementError("IG01-F evidence must be DEV+VALIDATION without HOLDOUT")
    if source.get("corpus_version") != "ig01f-recency-v1":
        raise MeasurementError("invalid IG01-F corpus version")
    if source_bound and (
        source.get("git_sha") != _source_git_sha()
        or source.get("source_fingerprint") != _fingerprint()
    ):
        raise MeasurementError("IG01-F evidence source fingerprint does not match frozen inputs")
    if set(report.get("providers", {})) != set(PROVIDERS):
        raise MeasurementError("IG01-F evidence must contain all providers")
    budget = _closed_mapping(
        report.get("budget"),
        {"max_context_tokens", "minimum_headroom_tokens", "usable_tokens", "hard_byte_limit", "estimator"},
        "budget",
    )
    if budget != {"max_context_tokens": 2048, "minimum_headroom_tokens": 128,
                  "usable_tokens": 1920, "hard_byte_limit": 24_000,
                  "estimator": "utf8-conservative-v1"}:
        raise MeasurementError("invalid IG01-F frozen budget")
    for provider in PROVIDERS:
        provider_report = report["providers"].get(provider)
        if not isinstance(provider_report, Mapping) or set(provider_report) != {
            "aggregate", "by_phenomenon", "by_language", "case_results", "controls"
        }:
            raise MeasurementError("invalid IG01-F provider evidence")
        aggregate = _validate_summary(provider_report["aggregate"], f"{provider} aggregate")
        for grouping_name in ("by_phenomenon", "by_language"):
            grouping = provider_report[grouping_name]
            if not isinstance(grouping, Mapping) or not grouping:
                raise MeasurementError(f"invalid IG01-F {provider} {grouping_name}")
            for group, summary in grouping.items():
                if not isinstance(group, str) or not group:
                    raise MeasurementError(f"invalid IG01-F {provider} {grouping_name} key")
                _validate_summary(summary, f"{provider} {grouping_name} {group}")
        case_results = provider_report["case_results"]
        if not isinstance(case_results, list) or len(case_results) != aggregate["case_count"]:
            raise MeasurementError("invalid IG01-F provider case results")
        case_ids = set()
        for row in case_results:
            row = _closed_mapping(row, {"case_id", "selected_ids", "metrics", "violations"}, "case result")
            case_id = row["case_id"]
            if not isinstance(case_id, str) or not case_id or case_id in case_ids:
                raise MeasurementError("invalid IG01-F case id")
            case_ids.add(case_id)
            if not isinstance(row["selected_ids"], list) or not all(isinstance(item, str) for item in row["selected_ids"]):
                raise MeasurementError("invalid IG01-F selected ids")
            if not isinstance(row["metrics"], Mapping) or not isinstance(row["violations"], list):
                raise MeasurementError("invalid IG01-F case metrics")
        controls = provider_report.get("controls")
        if not isinstance(controls, Mapping) or set(controls) != case_ids:
            raise MeasurementError("IG01-F anti-gaming controls are incomplete")
        for case_id, control in controls.items():
            if not isinstance(control, Mapping) or set(control) != {"select_all", "select_none"}:
                raise MeasurementError("invalid IG01-F anti-gaming control")
            if control["select_all"].get("case_id") != case_id:
                raise MeasurementError("IG01-F select_all control case mismatch")
            if control["select_none"].get("selected_ids") != []:
                raise MeasurementError("IG01-F select_none control is not empty")
        if provider == "recency" and any(provider_report["aggregate"]["leakage"].values()):
            raise MeasurementError("recency evidence contains leakage")
    if set(report.get("paired", {})) != {"recency_vs_v1", "recency_vs_v2"}:
        raise MeasurementError("invalid IG01-F paired evidence")
    for comparison, counts in report["paired"].items():
        counts = _closed_mapping(counts, {"wins", "ties", "losses"}, f"paired {comparison}")
        total = sum(_non_negative_int(counts[key], f"paired {comparison} {key}") for key in counts)
        if total != report["providers"]["recency"]["aggregate"]["case_count"]:
            raise MeasurementError("invalid IG01-F paired case count")
    abstention = _closed_mapping(report.get("abstention"), set(PROVIDERS), "abstention")
    for provider, counts in abstention.items():
        counts = _closed_mapping(counts, {"case_count", "empty_selection_count"}, f"{provider} abstention")
        case_count = _non_negative_int(counts["case_count"], f"{provider} abstention case_count")
        empty = _non_negative_int(counts["empty_selection_count"], f"{provider} empty_selection_count")
        if empty > case_count:
            raise MeasurementError("invalid IG01-F abstention count")
    if source_bound and _verify_regeneration:
        expected = _build_evidence_payload()
        if report != expected:
            raise MeasurementError("IG01-F evidence differs from deterministic regeneration")
    return dict(report)


def _build_evidence_payload() -> dict[str, Any]:
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
    provider_reports = {}
    for provider in PROVIDERS:
        ig01c_report = evaluate_corpus(
            cases,
            {case_id: {"retrieved_ids": selected} for case_id, selected in outputs[provider].items()},
            corpus_version="ig01f-recency-v1",
            split="dev+validation",
            retrieval_k=5,
            seed=0,
            source_fingerprint=_fingerprint(),
            git_sha=_source_git_sha(),
            enforce_benchmark=False,
        )
        validate_ig01c_report(ig01c_report)
        provider_reports[provider] = {
            "aggregate": _summary(list(evaluated[provider].values())),
            "by_phenomenon": _group(cases, evaluated[provider], "category"),
            "by_language": _group(cases, evaluated[provider], "language"),
            "case_results": [{
                "case_id": case_id,
                "selected_ids": outputs[provider][case_id],
                "metrics": evaluated[provider][case_id]["metrics"],
                "violations": evaluated[provider][case_id]["violations"],
            } for case_id in sorted(outputs[provider])],
            "controls": ig01c_report["controls"],
        }
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
    return report


def build_evidence() -> dict[str, Any]:
    return validate_evidence(_build_evidence_payload(), _verify_regeneration=False)


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
