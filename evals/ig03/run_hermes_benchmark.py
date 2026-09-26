"""One-off runner: score HermesCLIProvider on IG-03's frozen dev+validation
splits, same method benchmark.py already used for codex_cli/openai_api.

Not part of the frozen benchmark module itself -- benchmark_real_providers()
hardcodes the label "codex_cli" for whatever create_semantic_provider()
resolves to, which would mislabel Hermes results. This script reuses
benchmark_providers() (the per-split function) with an explicit, correctly
named provider map instead, then assembles the same real-provider report
shape benchmark.py would have produced.

Closes the "known limitation, not run" gap in
docs/history/reports/IG03-HERMES-CLI-LIVE-WIRING-REPORT.md.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from brain_eleven.extraction.semantic import DeterministicRegexProvider
from brain_eleven.extraction.providers import HermesCLIProvider
from evals.ig03.benchmark import CORPUS_ROOT, EXPECTED_CORPUS_VERSION, EXPECTED_DATASET_CLASS, _git_sha, benchmark_providers


def main() -> int:
    revision = _git_sha()
    hermes = HermesCLIProvider.from_environment()
    provider_map = {
        "regex": DeterministicRegexProvider(),
        "hermes_cli": hermes,
    }
    splits: dict[str, dict] = {}
    split_metadata: dict[str, dict] = {}
    for split in ("dev", "validation"):
        print(f"running split={split} ...", file=sys.stderr)
        split_report = benchmark_providers(split=split, providers=provider_map, corpus_root=CORPUS_ROOT, git_sha=revision)
        splits[split] = dict(split_report["providers"])
        split_metadata[split] = {
            "case_count": split_report["case_count"],
            "split_fingerprint": split_report["source"]["split_fingerprint"],
            "holdout_included": split_report["source"]["holdout_included"],
        }
        print(f"  done split={split}", file=sys.stderr)

    result = {
        "schema_version": 1,
        "report_type": "ig03_semantic_extraction_benchmark_real",
        "source": {
            "git_sha": revision,
            "corpus_version": EXPECTED_CORPUS_VERSION,
            "dataset_class": EXPECTED_DATASET_CLASS,
            "splits": ["dev", "validation"],
            "holdout_included": False,
            "split_metadata": split_metadata,
        },
        "providers": {
            name: {
                "splits": {split: splits[split][name] for split in ("dev", "validation")},
                "production_mutation": False,
            }
            for name in sorted(provider_map)
        },
    }
    output = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    rendered = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if output:
        output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
