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
from ..ig01c.metrics import evaluate_extraction_case
from brain_eleven.extraction.semantic import (
    DeterministicRegexProvider,
    SemanticProvider,
    UnavailableProvider,
)


ROOT = Path(__file__).resolve().parents[2]
CORPUS_ROOT = ROOT / "evals" / "ig01b" / "public" / "ig-eval-v2"
ALLOWED_SPLITS = frozenset({"dev", "validation"})


def _git_sha(root: Path = ROOT) -> str:
    return subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip().lower()


def _fingerprint(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def load_extraction_cases(*, split: str, corpus_root: Path | str = CORPUS_ROOT) -> list[dict[str, Any]]:
    """Load one public extraction split without touching HOLDOUT."""

    normalized = str(split).strip().lower()
    if normalized not in ALLOWED_SPLITS:
        raise ValueError("IG-03 benchmark accepts only dev or validation")
    path = Path(corpus_root).resolve() / f"{normalized}.jsonl"
    cases = [case for case in load_cases(path) if case.get("family") == "extraction"]
    if not cases:
        raise ValueError(f"{path} has no extraction cases")
    if any(case.get("split") != normalized or "holdout" in case.get("case_id", "").lower() for case in cases):
        raise ValueError("public extraction split contains an invalid or holdout case")
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


def _run_provider(provider: SemanticProvider, cases: list[Mapping[str, Any]]) -> dict[str, Any]:
    started = time.perf_counter()
    case_rows: list[dict[str, Any]] = []
    statuses: defaultdict[str, int] = defaultdict(int)
    for case in cases:
        result = provider.extract(_message(case))
        statuses[result.status] += 1
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
    return {
        "provider": {"id": provider.provider_id, "model": provider.model, "production_mutation": False},
        "status_counts": dict(sorted(statuses.items())),
        "metrics": {name: _aggregate(case_rows, name) for name in metric_names},
        "safety": {
            "event_count": len(safety_events),
            "gates": sorted({event["gate"] for event in safety_events}),
        },
        "measurement": {
            "case_count": len(cases),
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

    cases = load_extraction_cases(split=split, corpus_root=corpus_root)
    revision = (git_sha or _git_sha(ROOT)).lower()
    if not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise ValueError("git_sha must be a full lowercase 40-character SHA")
    provider_map = dict(providers or {
        "regex": DeterministicRegexProvider(),
        "local_qwen": UnavailableProvider("local-qwen", "unconfigured"),
        "strong": UnavailableProvider("strong-model", "unconfigured"),
    })
    result = {
        "schema_version": 1,
        "report_type": "ig03_semantic_extraction_benchmark",
        "source": {
            "git_sha": revision,
            "corpus_version": "ig-eval-v2",
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
