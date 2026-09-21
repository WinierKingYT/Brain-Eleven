"""Build the public-only, time-aware IG01-F canonical-store projection."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[2]
SOURCE_ROOT = ROOT / "evals" / "ig01b" / "public" / "ig-eval-v2"
DEFAULT_OUTPUT = ROOT / "evals" / "ig01f" / "public" / "ig01f-recency-v1"
SOURCE_FILES = {"dev": "dev.jsonl", "validation": "validation.jsonl", "abstention": "abstention.jsonl"}
HOSTILE = frozenset(
    {
        "hypothetical",
        "question",
        "negation",
        "quoted_material",
        "assistant_proposal",
        "old_critical_decision",
        "irrelevant_recent_memory",
    }
)
FAVORABLE = frozenset({"explicit_decision", "preference", "requirement", "correction"})

_TEMPLATES = {
    "en": ("Current project record for {category}.", "Alternative recent context for {category}."),
    "tr": ("{category} için güncel proje kaydı.", "{category} için alternatif yakın bağlam."),
    "tr-en": ("{category} için current project record.", "{category} için alternative recent context."),
}


class CorpusProjectionError(RuntimeError):
    """Raised when the frozen public-only projection boundary is violated."""


def _safe_source_path(root: Path, split: str) -> Path:
    if "holdout" in split.casefold() or split not in SOURCE_FILES:
        raise CorpusProjectionError("IG01-F projection refuses HOLDOUT and unknown splits")
    path = (root / SOURCE_FILES[split]).resolve()
    if "holdout" in path.name.casefold() or path.parent != root.resolve():
        raise CorpusProjectionError("IG01-F source path escaped its public boundary")
    return path


def _load_rows(root: Path, split: str) -> list[dict[str, Any]]:
    path = _safe_source_path(root, split)
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        value = json.loads(line)
        if not isinstance(value, dict) or value.get("split") not in {split, "dev", "validation"}:
            raise CorpusProjectionError(f"invalid source row in {split}")
        rows.append(value)
    return rows


def _opaque_id(case_id: str, ordinal: int) -> str:
    digest = hashlib.sha256(f"{case_id}\0{ordinal}".encode()).hexdigest()[:20]
    return f"mem-ig01f-{digest}"


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _event_time(row: Mapping[str, Any]) -> datetime:
    lineage = row.get("data_lineage")
    raw = lineage.get("event_time") if isinstance(lineage, Mapping) else None
    if not isinstance(raw, str):
        raise CorpusProjectionError("source row lacks event_time")
    return datetime.fromisoformat(raw.replace("Z", "+00:00"))


def _timestamps(category: str, event: datetime, ordinal: int, case_id: str) -> tuple[str, str]:
    if category in HOSTILE:
        days = -120 if ordinal == 0 else 1
    elif category in FAVORABLE:
        days = 1 if ordinal == 0 else -120
    else:
        # Neutral ordering is independent of answer labels and source ID suffixes.
        days = -30 + (int(hashlib.sha256(f"{case_id}:{ordinal}".encode()).hexdigest()[:4], 16) % 60)
    created = event + timedelta(days=days - 7)
    updated = event + timedelta(days=days)
    return _iso(created), _iso(updated)


def _candidate_count(row: Mapping[str, Any]) -> int:
    candidates = row.get("candidate_ids")
    if not isinstance(candidates, list) or len(candidates) < 2:
        return 2
    return len(candidates)


def project_row(row: Mapping[str, Any], split: str) -> dict[str, Any]:
    case_id = str(row["case_id"])
    category = str(row["category"])
    language = str(row["language"])
    project_id = str(row.get("project_id") or "project-a")
    event = _event_time(row)
    original_ids = list(row.get("candidate_ids") or ())
    count = _candidate_count(row)
    mapped = {
        original_ids[index] if index < len(original_ids) else f"generated-{index}": _opaque_id(case_id, index)
        for index in range(count)
    }
    templates = _TEMPLATES.get(language)
    if templates is None:
        raise CorpusProjectionError(f"unsupported language: {language}")
    memories = []
    forbidden_source_ids = set(row.get("forbidden_ids") or ())
    for index in range(count):
        created_at, updated_at = _timestamps(category, event, index, case_id)
        status = "active"
        candidate_project = project_id
        if index == 1 and category == "wrong_project_candidate":
            candidate_project = "project-foreign"
        elif index == 1 and category == "superseded_memory":
            status = "superseded"
        elif index == 1 and category == "resolved_blocker":
            status = "resolved"
        content = templates[min(index, 1)].format(category=category.replace("_", " "))
        original_id = original_ids[index] if index < len(original_ids) else f"generated-{index}"
        record = (
            {
                "memory_id": _opaque_id(case_id, index),
                "type": "decision" if category in {"explicit_decision", "old_critical_decision", "correction"} else "observation",
                "content": content,
                "confidence": 1.0,
                "quality_score": 1.0,
                "source": "ig01f_public_projection",
                "timestamp": updated_at,
                "created_at": created_at,
                "updated_at": updated_at,
                "related_notes": [],
                "section": "IG01-F synthetic projection",
                "issues": [],
                "novelty": 1.0,
                "is_approved": True,
                "status": status,
                "resolved_at": updated_at if status == "resolved" else "",
                "resolved_by": "ig01f-fixture" if status == "resolved" else "",
                "resolution_note": "fixture lifecycle" if status == "resolved" else "",
                "superseded_by": _opaque_id(case_id, 0) if status == "superseded" else "",
                "supersession_note": "fixture lifecycle" if status == "superseded" else "",
                "dedup_fingerprint": hashlib.sha256(content.encode()).hexdigest(),
                "scope": "project",
                "project": candidate_project,
                "project_label": candidate_project,
                "project_id": candidate_project,
            }
        )
        # Forbidden labels represent records rejected before canonical admission;
        # they remain evaluator candidates but never enter MemoryStore.
        if original_id not in forbidden_source_ids:
            memories.append(record)

    def ids(name: str) -> list[str]:
        values = row.get(name) or ()
        return [mapped[value] for value in values if value in mapped]

    return {
        "schema_version": 1,
        "corpus_version": "ig01f-recency-v1",
        "source_corpus_version": "ig-eval-v2",
        "split": split,
        "case_id": case_id,
        "family": "retrieval",
        "source_family": row.get("family"),
        "case_kind": "abstention" if split == "abstention" else "answerable",
        "answerability": {"status": "unanswerable" if split == "abstention" else "answerable"},
        "category": category,
        "language": language,
        "project_id": project_id,
        "task_text": str(row.get("query") or f"{category} continuity"),
        "candidate_ids": [item["memory_id"] for item in memories],
        "required_ids": ids("required_ids"),
        "acceptable_ids": ids("acceptable_ids"),
        "mandatory_ids": ids("mandatory_ids"),
        "forbidden_ids": ids("forbidden_ids"),
        "memories": memories,
    }


def _render(rows: Iterable[Mapping[str, Any]]) -> bytes:
    return ("".join(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n" for row in rows)).encode("utf-8")


def build_projection(source_root: Path = SOURCE_ROOT) -> dict[str, bytes]:
    outputs: dict[str, bytes] = {}
    counts: dict[str, int] = {}
    for split in ("dev", "validation", "abstention"):
        projected = [project_row(row, split) for row in _load_rows(source_root, split)]
        outputs[f"{split}.jsonl"] = _render(projected)
        counts[split] = len(projected)
    manifest = {
        "schema_version": 1,
        "corpus_version": "ig01f-recency-v1",
        "source_corpus_version": "ig-eval-v2",
        "source_splits": ["dev", "validation", "abstention"],
        "holdout_included": False,
        "counts": counts,
        "files": {name: f"sha256:{hashlib.sha256(payload).hexdigest()}" for name, payload in outputs.items()},
    }
    outputs["manifest.json"] = (json.dumps(manifest, sort_keys=True, indent=2) + "\n").encode()
    return outputs


def write_projection(output: Path = DEFAULT_OUTPUT, source_root: Path = SOURCE_ROOT) -> None:
    output.mkdir(parents=True, exist_ok=True)
    expected = build_projection(source_root)
    for name, payload in expected.items():
        (output / name).write_bytes(payload)


def check_projection(output: Path = DEFAULT_OUTPUT, source_root: Path = SOURCE_ROOT) -> None:
    expected = build_projection(source_root)
    actual = {path.name: path.read_bytes() for path in output.iterdir() if path.is_file()}
    if actual != expected:
        raise CorpusProjectionError("committed IG01-F projection differs from deterministic public inputs")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    if args.check:
        check_projection(args.output)
    else:
        write_projection(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
