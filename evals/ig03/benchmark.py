"""Content-free IG-03 provider benchmark.

The runner deliberately loads only the requested public DEV or VALIDATION
split.  It never opens the sealed IG01-B HOLDOUT and never writes production
state.  Providers return proposal objects; IG01-C remains the metric authority.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import re
import subprocess
import time
from typing import Any, Iterable, Mapping

from ..ig01b.schema import load_cases
from ..ig01c.metrics import evaluate_extraction_case, expected_calibration_error
from brain_eleven.extraction.semantic import (
    DeterministicRegexProvider,
    SemanticProvider,
    UnavailableProvider,
)
from brain_eleven.extraction.providers import create_semantic_provider


ROOT = Path(__file__).resolve().parents[2]
CORPUS_ROOT = ROOT / "evals" / "ig01b" / "public" / "ig-eval-v2"
ALLOWED_SPLITS = frozenset({"dev", "validation"})
EXPECTED_CORPUS_VERSION = "ig-eval-v2"
EXPECTED_DATASET_CLASS = "PUBLIC_SYNTHETIC"


def _git_sha(root: Path = ROOT) -> str:
    return subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip().lower()


def _fingerprint(path: Path) -> str:
    """Hash logical JSONL content independent of checkout line endings.

    The public corpus manifest is generated from LF-delimited JSONL.  Git may
    materialize tracked text files with CRLF on Windows, so hashing raw bytes
    would make an unchanged split appear tampered with on that runner.  The
    canonical fingerprint is therefore computed from normalized LF bytes.
    """

    content = path.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    return "sha256:" + hashlib.sha256(content).hexdigest()


def _load_public_corpus(*, split: str, corpus_root: Path | str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Load an immutable public split and verify its manifest provenance."""

    normalized = str(split).strip().lower()
    if normalized not in ALLOWED_SPLITS:
        raise ValueError("IG-03 benchmark accepts only dev or validation")
    root = Path(corpus_root).resolve()
    manifest_path = root / "manifest.json"
    if not manifest_path.is_file():
        raise ValueError("public corpus manifest.json is required")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError("public corpus manifest is unreadable") from error
    if not isinstance(manifest, Mapping):
        raise ValueError("public corpus manifest must be an object")
    if manifest.get("corpus_version") != EXPECTED_CORPUS_VERSION:
        raise ValueError("IG-03 requires the current frozen corpus version")
    if manifest.get("dataset_class") != EXPECTED_DATASET_CLASS:
        raise ValueError("IG-03 requires a public synthetic corpus")
    path = root / f"{normalized}.jsonl"
    if not path.is_file():
        raise ValueError(f"missing corpus split: {path}")
    expected_hash = ((manifest.get("file_sha256") or {}).get(normalized))
    if not isinstance(expected_hash, str) or expected_hash != _fingerprint(path).removeprefix("sha256:"):
        raise ValueError("corpus split fingerprint does not match its manifest")
    cases = [case for case in load_cases(path, expected_class=EXPECTED_DATASET_CLASS) if case.get("family") == "extraction"]
    if not cases:
        raise ValueError(f"{path} has no extraction cases")
    if any(
        case.get("corpus_version") != EXPECTED_CORPUS_VERSION
        or case.get("split") != normalized
        or "holdout" in case.get("case_id", "").lower()
        for case in cases
    ):
        raise ValueError("public extraction split contains an invalid or holdout case")
    return cases, dict(manifest)


def load_extraction_cases(*, split: str, corpus_root: Path | str = CORPUS_ROOT) -> list[dict[str, Any]]:
    """Load one public extraction split without touching HOLDOUT."""

    cases, _ = _load_public_corpus(split=split, corpus_root=corpus_root)
    return cases


def _message(case: Mapping[str, Any]) -> dict[str, Any]:
    conversation = case.get("conversation") or []
    if not conversation:
        raise ValueError(f"{case.get('case_id')} has no conversation")
    # The public extraction corpus currently uses one turn per case.  For a
    # future mixed-turn case, unknown role is safer than promoting one role to
    # the whole conversation.
    roles = {str(turn.get("role", "unknown")).lower() for turn in conversation}
    role = next(iter(roles)) if len(roles) == 1 else "unknown"
    text = "\n".join(str(turn.get("text", "")) for turn in conversation)
    return {
        "content": text,
        "role": role,
        "project_id": case.get("project_id"),
        "evidence_id": (case.get("evidence_refs") or [case["case_id"]])[0],
        "occurred_at": None,
    }


def _prediction(result: Any) -> dict[str, Any]:
    if not result.propositions:
        return {}
    proposition = result.propositions[0].to_dict()
    # IG01-C accepts the corpus vocabulary while the proposition keeps the
    # frozen IG01-A field names.  These are derived aliases, not new authority.
    proposition["memory_type"] = proposition.get("claim_type")
    proposition["scope"] = "project-local" if proposition.get("project_id") else "unresolved"
    proposition["state_operation"] = "ADD"
    proposition["correction"] = bool(proposition.get("correction_clues"))
    proposition["target_behavior"] = "none"
    proposition["canonical_commit"] = False
    proposition["confidence"] = getattr(result.propositions[0], "confidence", None)
    if proposition.get("commitment") == "committed":
        proposition["commitment"] = "explicit"
    elif proposition.get("commitment") in {"proposed", "hypothetical", "question", "negated", "quoted", "uncertain"}:
        proposition["commitment"] = "none"
    return proposition


def _aggregate(rows: Iterable[Mapping[str, Any]], metric_name: str) -> dict[str, Any]:
    values = [row["metrics"][metric_name] for row in rows if metric_name in row.get("metrics", {})]
    applicable = [value for value in values if not value.get("not_applicable")]
    numerator = sum(float(value.get("numerator", 0)) for value in applicable)
    denominator = sum(float(value.get("denominator", 0)) for value in applicable)
    if not applicable:
        return {"value": None, "numerator": numerator, "denominator": denominator, "not_applicable": True, "empty_selection": False}
    return {
        "value": sum(float(value["value"]) for value in applicable) / len(applicable),
        "numerator": numerator,
        "denominator": denominator,
        "not_applicable": False,
        "empty_selection": any(value.get("empty_selection", False) for value in applicable),
    }


def _not_applicable_metric() -> dict[str, Any]:
    return {"value": None, "numerator": 0, "denominator": 0, "not_applicable": True, "empty_selection": False}


def _run_provider(provider: SemanticProvider, cases: list[Mapping[str, Any]]) -> dict[str, Any]:
    started = time.perf_counter()
    case_rows: list[dict[str, Any]] = []
    statuses: defaultdict[str, int] = defaultdict(int)
    provenance: set[tuple[Any, ...]] = set()
    for case in cases:
        result = provider.extract(_message(case))
        statuses[result.status] += 1
        metadata = dict(result.metadata)
        provenance.add((
            result.schema_version,
            metadata.get("requested_schema_version"),
            metadata.get("provider_revision"),
            metadata.get("availability_code"),
            metadata.get("project_bound"),
        ))
        if result.status == "SEMANTIC_UNAVAILABLE":
            continue
        row = evaluate_extraction_case(case, _prediction(result))
        case_rows.append(row)
    metric_names = (
        "decision_precision",
        "decision_recall",
        "false_commitment_rate",
        "assistant_as_user_rate",
        "wrong_type_rate",
        "wrong_scope_rate",
        "ece",
    )
    safety_events = [event for row in case_rows for event in row.get("safety_events", [])]
    ece_samples = [
        (float(row["ece_sample"]["confidence"]), bool(row["ece_sample"]["correct"]))
        for row in case_rows if row.get("ece_sample") is not None
    ]
    metrics = {name: _aggregate(case_rows, name) for name in metric_names if name != "ece"}
    metrics["ece"] = expected_calibration_error(ece_samples).as_dict() if ece_samples else _not_applicable_metric()
    return {
        "provider": {
            "id": provider.provider_id,
            "model": provider.model,
            "production_mutation": False,
            "provenance": [
                {
                    "schema_version": item[0],
                    "requested_schema_version": item[1],
                    "provider_revision": item[2],
                    "availability_code": item[3],
                    "project_bound": item[4],
                }
                for item in sorted(provenance, key=repr)
            ],
        },
        "status_counts": dict(sorted(statuses.items())),
        "metrics": metrics,
        "safety": {
            "event_count": len(safety_events),
            "gates": sorted({event["gate"] for event in safety_events}),
        },
        "measurement": {
            "case_count": len(cases),
            "applicable_case_count": len(case_rows),
            "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
        },
    }


def benchmark_providers(
    *,
    split: str = "dev",
    providers: Mapping[str, SemanticProvider] | None = None,
    corpus_root: Path | str = CORPUS_ROOT,
    git_sha: str | None = None,
) -> dict[str, Any]:
    """Benchmark all configured provider slots on one public extraction split."""

    cases, manifest = _load_public_corpus(split=split, corpus_root=corpus_root)
    revision = (git_sha or _git_sha(ROOT)).lower()
    if not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise ValueError("git_sha must be a full lowercase 40-character SHA")
    actual_revision = _git_sha(ROOT)
    if revision != actual_revision:
        raise ValueError("git_sha must match the exact repository HEAD")
    if providers is not None:
        provider_map = dict(providers)
    else:
        provider_map = {
            "regex": DeterministicRegexProvider(),
            "local_qwen": UnavailableProvider("local-qwen", "unconfigured"),
            "strong": UnavailableProvider("strong-model", "unconfigured"),
        }
        # The existing slots remain unavailable by default. An explicitly
        # configured provider is an opt-in benchmark input for R1 only.
        configured = create_semantic_provider()
        if configured.provider_id != "unavailable":
            provider_map["configured"] = configured
    result = {
        "schema_version": 1,
        "report_type": "ig03_semantic_extraction_benchmark",
        "source": {
            "git_sha": revision,
            "corpus_version": manifest["corpus_version"],
            "dataset_class": manifest["dataset_class"],
            "split": split,
            "split_fingerprint": _fingerprint(Path(corpus_root).resolve() / f"{split}.jsonl"),
            "holdout_included": False,
        },
        "providers": {name: _run_provider(provider, cases) for name, provider in sorted(provider_map.items())},
        "case_count": len(cases),
    }
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the content-free IG-03 extraction benchmark")
    parser.add_argument("--split", choices=sorted(ALLOWED_SPLITS), default="dev")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    report = benchmark_providers(split=args.split)
    rendered = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
