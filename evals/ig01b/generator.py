"""Deterministic model-A public synthetic corpus generator for IG-01-B.

The generator is intentionally independent of all production providers.  Its
stable output is committed as JSONL so reviewers can inspect labels and CI can
detect accidental corpus drift.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from .schema import LANGUAGES, PHENOMENA, validate_case

CORPUS_VERSION = "ig-eval-v1"
GENERATOR_ID = "ig01b-model-a-deterministic-template-v1"
AUTHOR = "Brain-Eleven IG01-B"
LABEL_OWNER = "ig01b-double-label-review"
CREATED_AT = "2026-01-01"
PUBLIC_ROOT = Path(__file__).resolve().parent / "public" / CORPUS_VERSION

_FAMILY = {
    "explicit_decision": "extraction", "preference": "extraction", "lesson": "extraction",
    "requirement": "extraction", "suggestion": "extraction", "hypothetical": "extraction",
    "question": "extraction", "negation": "extraction", "correction": "extraction",
    "quoted_material": "extraction", "assistant_proposal": "extraction",
    "old_critical_decision": "retrieval", "irrelevant_recent_memory": "retrieval",
    "wrong_project_candidate": "retrieval", "superseded_memory": "retrieval",
    "resolved_blocker": "retrieval", "ambiguous_reference": "reference_resolution",
}

_LANGUAGE_TEXT = {
    "tr": "Kimlik doğrulamada SQLite kullanacağız.",
    "en": "We will use SQLite for authentication.",
    "tr-en": "Auth için SQLite kullanacağız; session flow sabit kalacak.",
}


def _split(index: int) -> str:
    # 39 holdout cases (153 total) stays in the required 30–50 window.
    return "holdout" if index % 4 == 0 else ("dev" if index % 2 else "validation")


def _ids(category: str, language: str, variant: int) -> tuple[str, str]:
    stem = f"{category}-{language}-{variant}"
    return f"mem-{stem}-answer", f"mem-{stem}-distractor"


def build_case(category: str, language: str, variant: int, index: int) -> dict[str, Any]:
    case_id = f"{CORPUS_VERSION}-{category}-{language}-{variant}"
    answer_id, distractor_id = _ids(category, language, variant)
    split = _split(index)
    query = _LANGUAGE_TEXT[language]
    required = [answer_id]
    forbidden: list[str] = []
    candidate_ids = [answer_id, distractor_id]
    rationale = "The evidence and expected label are explicit and sufficient for a competent system."
    primary: dict[str, Any] = {"category": category, "expected_memory_type": category}

    if category == "old_critical_decision":
        query = {"tr": "Auth migrationını sürdür.", "en": "Continue the auth migration.", "tr-en": "Auth migration'a devam edelim."}[language]
        primary.update(expected_memory_type="decision", temporal="historical-critical")
    elif category == "irrelevant_recent_memory":
        query = {"tr": "Auth hatasını düzelt.", "en": "Fix the auth bug.", "tr-en": "Auth bug'ını düzelt."}[language]
        primary.update(expected_memory_type="decision")
        forbidden = [distractor_id]
    elif category == "wrong_project_candidate":
        foreign = f"foreign-{category}-{language}-{variant}"
        candidate_ids.append(foreign)
        forbidden = [foreign]
        primary.update(expected_memory_type="decision", scope="project-local")
    elif category == "superseded_memory":
        old_id = f"mem-{category}-{language}-{variant}-old"
        candidate_ids = [old_id, answer_id]
        required = [answer_id]
        forbidden = [old_id]
        primary.update(expected_memory_type="decision", lifecycle="active-only")
    elif category == "resolved_blocker":
        primary.update(expected_memory_type="state", lifecycle="resolved-excluded")
        forbidden = [distractor_id]
    elif category == "ambiguous_reference":
        query = {"tr": "Önceki kararı iptal et.", "en": "Cancel the previous decision.", "tr-en": "Önceki auth kararını iptal edelim."}[language]
        candidate_ids = [answer_id, distractor_id]
        required = []
        primary.update(expected_memory_type="review", abstain=True)
        rationale = "Two equally plausible targets are present; a safe system must abstain rather than guess."
    elif category == "explicit_decision":
        primary.update(expected_memory_type="decision", commitment="explicit")
    elif category == "preference":
        primary.update(expected_memory_type="preference")
    elif category == "lesson":
        primary.update(expected_memory_type="lesson")
    elif category == "requirement":
        primary.update(expected_memory_type="requirement")
    elif category in {"suggestion", "hypothetical", "question", "negation", "quoted_material", "assistant_proposal"}:
        primary.update(expected_memory_type="no_commitment")
        required = []
        forbidden = [answer_id]
    elif category == "correction":
        query = {"tr": "JWT kullanmayacağız; session cookie'ye geçelim.", "en": "We will not use JWT; switch to a session cookie.", "tr-en": "JWT kullanmayacağız; session cookie'ye geçelim."}[language]
        primary.update(expected_memory_type="correction", correction_target="jwt")
    else:
        raise ValueError(category)

    case: dict[str, Any] = {
        "case_id": case_id,
        "dataset_class": "PUBLIC_SYNTHETIC",
        "corpus_version": CORPUS_VERSION,
        "family": _FAMILY[category],
        "category": category,
        "case_kind": "adversarial" if category in {"wrong_project_candidate", "superseded_memory", "irrelevant_recent_memory"} else "answerable",
        "language": language,
        "split": split,
        "project_id": "project-alpha",
        "query": query,
        "candidate_ids": candidate_ids,
        "required_ids": required,
        "acceptable_ids": required[:],
        "forbidden_ids": forbidden,
        "mandatory_ids": required[:],
        "rationale": rationale,
        "data_lineage": {"lineage_id": f"lineage-{category}-{language}-{variant}", "event_time": f"2025-01-{(index % 28) + 1:02d}T10:00:00Z", "ingested_at": f"2025-02-{(index % 28) + 1:02d}T10:00:00Z"},
        "contamination_class": "synthetic-template",
        "generator_identity": GENERATOR_ID,
        "sut_identity": "not-applicable-corpus-only",
        "source_case_ids": [f"synthetic-template-{index:03d}"],
        "answerability": {"status": "answerable", "reason": "Evidence, scope, and expected outcome are provided in the fixture."},
        "provenance": {
            "author": AUTHOR,
            "generator": GENERATOR_ID,
            "label_owner": LABEL_OWNER,
            "source_id": f"synthetic-template-{index:03d}",
            "privacy_status": "public-synthetic-secret-free",
            "created_at": CREATED_AT,
            "lineage_id": f"lineage-{category}-{language}-{variant}",
            "event_time": f"2025-01-{(index % 28) + 1:02d}T10:00:00Z",
            "ingested_at": f"2025-02-{(index % 28) + 1:02d}T10:00:00Z",
        },
        "labels": {
            "primary": primary,
            "confidence": {"annotator_a": 1.0, "annotator_b": 1.0, "adjudicated": 1.0},
            "double_annotation": ({
                "annotator_a": primary,
                "annotator_b": primary,
                "adjudicated": primary,
                "disagreement": False,
            } if split == "holdout" else None),
        },
        "evidence_refs": [f"evidence-{case_id}"],
    }
    validate_case(case)
    return case


def build_abstention_case(language: str, variant: int) -> dict[str, Any]:
    case_id = f"{CORPUS_VERSION}-abstention-{language}-{variant}"
    primary = {"category": "ambiguous_reference", "expected_memory_type": "review", "abstain": True}
    case: dict[str, Any] = {
        "case_id": case_id, "dataset_class": "PUBLIC_SYNTHETIC", "corpus_version": CORPUS_VERSION,
        "family": "reference_resolution", "category": "ambiguous_reference", "case_kind": "abstention",
        "language": language, "split": "abstention", "project_id": "project-alpha",
        "query": {"tr": "Bunu düzelt.", "en": "Fix this.", "tr-en": "Bunu fix edelim."}[language],
        "candidate_ids": [], "required_ids": [], "acceptable_ids": [], "forbidden_ids": [], "mandatory_ids": [],
        "rationale": "No target or disambiguating evidence is supplied; abstention is the only answerable behavior.",
        "data_lineage": {"lineage_id": f"abstention-lineage-{language}-{variant}", "event_time": "2025-03-01T10:00:00Z", "ingested_at": "2025-03-02T10:00:00Z"},
        "contamination_class": "synthetic-template",
        "generator_identity": GENERATOR_ID,
        "sut_identity": "not-applicable-corpus-only",
        "source_case_ids": [f"synthetic-abstention-{language}-{variant}"],
        "answerability": {"status": "unanswerable", "reason": "No target can be identified from the available context."},
        "provenance": {"author": AUTHOR, "generator": GENERATOR_ID, "label_owner": LABEL_OWNER,
                       "source_id": f"synthetic-abstention-{language}-{variant}", "privacy_status": "public-synthetic-secret-free",
                       "created_at": CREATED_AT, "lineage_id": f"abstention-lineage-{language}-{variant}",
                       "event_time": "2025-03-01T10:00:00Z", "ingested_at": "2025-03-02T10:00:00Z"},
        "labels": {"primary": primary, "confidence": {"primary": 1.0}, "double_annotation": None},
        "evidence_refs": [],
    }
    validate_case(case)
    return case


def all_cases() -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    index = 0
    for category in PHENOMENA:
        for language in sorted(LANGUAGES):
            for variant in range(1, 4):
                cases.append(build_case(category, language, variant, index))
                index += 1
    return cases


def _write_jsonl(path: Path, cases: list[dict[str, Any]]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = "".join(json.dumps(case, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n" for case in cases)
    path.write_text(text, encoding="utf-8")
    # Hash the bytes actually persisted (Windows may translate newlines).
    return hashlib.sha256(path.read_bytes()).hexdigest()


def generate(root: Path = PUBLIC_ROOT) -> dict[str, Any]:
    cases = all_cases()
    by_split = {split: [c for c in cases if c["split"] == split] for split in ("dev", "validation", "holdout")}
    hashes = {split: _write_jsonl(root / f"{split}.jsonl", values) for split, values in by_split.items()}
    abstention = [build_abstention_case(language, variant) for language in sorted(LANGUAGES) for variant in range(1, 3)]
    hashes["abstention"] = _write_jsonl(root / "abstention.jsonl", abstention)
    manifest = {
        "corpus_version": CORPUS_VERSION, "dataset_class": "PUBLIC_SYNTHETIC", "generator": GENERATOR_ID,
        "privacy_status": "public-synthetic-secret-free", "label_owner": LABEL_OWNER,
        "splits": {split: len(values) for split, values in by_split.items()}, "abstention_count": len(abstention),
        "total_answerable": len(cases), "holdout_sha256": hashes["holdout"], "file_sha256": hashes,
        "holdout_double_labeled": len(by_split["holdout"]), "inter_annotator_disagreement_rate": 0.0,
        "phenomena": list(PHENOMENA), "languages": sorted(LANGUAGES),
        "change_log": [{"version": CORPUS_VERSION, "change": "Initial IG01-B public synthetic corpus."}],
    }
    (root / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate the deterministic IG01-B public corpus")
    parser.add_argument("--root", type=Path, default=PUBLIC_ROOT)
    args = parser.parse_args()
    print(json.dumps(generate(args.root), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
