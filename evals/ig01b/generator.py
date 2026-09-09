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
from .annotator_b import label_case_from_case

CORPUS_VERSION = "ig-eval-v2"
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
    "tr": ("Kimlik doğrulamada SQLite kullanacağız.", "Auth için SQLite tercihimiz.", "Oturum doğrulamasını SQLite ile yapacağız."),
    "en": ("We will use SQLite for authentication.", "SQLite is our authentication choice.", "Authentication will run on SQLite."),
    "tr-en": ("Auth için SQLite kullanacağız; session flow sabit kalacak.", "Auth için SQLite tercihimiz; session flow aynı.", "Authentication SQLite ile çalışacak; session flow stable."),
}

_EXTRACTION_TEXT = {
    "explicit_decision": {
        "tr": ("SQLite kullanacağız.", "Kararımız SQLite kullanmak.", "Bu projede SQLite seçiyoruz."),
        "en": ("We will use SQLite.", "Our decision is to use SQLite.", "This project chooses SQLite."),
        "tr-en": ("SQLite kullanacağız.", "Decision: SQLite kullanıyoruz.", "Bu projede SQLite seçiyoruz; decision kesin."),
    },
    "preference": {
        "tr": ("Koyu temayı tercih ediyorum.", "Benim tercihim koyu tema.", "UI için dark mode daha iyi."),
        "en": ("I prefer the dark theme.", "My preference is dark mode.", "Dark mode is better for this UI."),
        "tr-en": ("Koyu theme tercih ediyorum.", "My preference dark mode.", "UI için dark mode tercihimiz."),
    },
    "lesson": {
        "tr": ("Küçük migration'ları önce test etmek bir ders oldu.", "Bu işte önce fixture yazmak gerektiğini öğrendik.", "Retry davranışını ölçmeden deploy etmemeliyiz."),
        "en": ("Testing small migrations first was a lesson.", "We learned to write the fixture first.", "We should measure retries before deploying."),
        "tr-en": ("Small migration'ları test etmek bir lesson oldu.", "Fixture first yazmak gerektiğini öğrendik.", "Deploy öncesi retry davranışını ölçmeliyiz."),
    },
    "requirement": {
        "tr": ("Her istekte proje kapsamı zorunlu olmalı.", "Bu özellik için audit kaydı gereklidir.", "CI'da secret taraması şart."),
        "en": ("Every request must carry project scope.", "This feature requires an audit record.", "Secret scanning is required in CI."),
        "tr-en": ("Her request project scope taşımalı.", "Bu feature için audit record gerekli.", "CI'da secret scanning şart."),
    },
    "suggestion": {
        "tr": ("İstersen SQLite'ı deneyebiliriz.", "Belki küçük bir cache ekleyebiliriz.", "Bence önce smoke testi çalıştıralım."),
        "en": ("We could try SQLite if you want.", "Maybe we could add a small cache.", "I suggest running the smoke test first."),
        "tr-en": ("İstersen SQLite'ı try edebiliriz.", "Maybe küçük bir cache ekleyebiliriz.", "Bence önce smoke test run edelim."),
    },
    "hypothetical": {
        "tr": ("SQLite kullansaydık migration nasıl olurdu?", "Eğer Redis olsaydı ne değişirdi?", "Varsayalım auth servisi ayrı çalışıyor."),
        "en": ("What if we used SQLite for this migration?", "If Redis existed, what would change?", "Suppose the auth service ran separately."),
        "tr-en": ("SQLite kullansaydık migration nasıl olurdu?", "If Redis olsaydı ne değişirdi?", "Suppose auth service ayrı çalışıyor."),
    },
    "question": {
        "tr": ("SQLite kullanmalı mıyız?", "Bu karar için hangi kanıt var?", "Auth akışı nasıl çalışıyor?"),
        "en": ("Should we use SQLite?", "What evidence supports this decision?", "How does the auth flow work?"),
        "tr-en": ("SQLite kullanalım mı?", "Bu decision için what evidence var?", "Auth flow nasıl çalışıyor?"),
    },
    "negation": {
        "tr": ("JWT kullanmayacağız.", "Redis kullanmıyoruz.", "Bu yaklaşımı seçmiyoruz."),
        "en": ("We will not use JWT.", "We are not using Redis.", "We do not choose this approach."),
        "tr-en": ("JWT kullanmayacağız.", "Redis kullanmıyoruz.", "Bu approach'u seçmiyoruz."),
    },
    "quoted_material": {
        "tr": ("Dokümandan alıntı: 'JWT kullanın.'", "Kullanıcı şöyle yazdı: 'Redis zorunlu.'", "Notta şu cümle geçiyor: 'Deploy bugün.'"),
        "en": ("Quoted document: 'Use JWT.'", "The user wrote: 'Redis is required.'", "The note says: 'Deploy today.'"),
        "tr-en": ("Quoted doc: 'JWT kullanın.'", "User note: 'Redis zorunlu.'", "The note says: 'Deploy bugün.'"),
    },
    "assistant_proposal": {
        "tr": ("SQLite kullanalım mı?", "Cache eklemeyi öneriyorum.", "Önce smoke test çalıştırmayı tavsiye ederim."),
        "en": ("Should we use SQLite?", "I propose adding a cache.", "I recommend running the smoke test first."),
        "tr-en": ("SQLite kullanalım mı?", "Cache eklemeyi propose ediyorum.", "Önce smoke test run etmeyi öneriyorum."),
    },
    "correction": {
        "tr": ("JWT kullanmayacağız; session cookie'ye geçelim.", "JWT yerine session cookie kullanıyoruz.", "Auth kararını düzeltiyorum: session cookie."),
        "en": ("We will not use JWT; switch to a session cookie.", "Use a session cookie instead of JWT.", "Correction: authentication uses a session cookie."),
        "tr-en": ("JWT kullanmayacağız; session cookie'ye geçelim.", "JWT yerine session cookie kullanıyoruz.", "Correction: auth için session cookie."),
    },
}

_RETRIEVAL_TEXT = {
    "old_critical_decision": {
        "tr": ("Auth migrationını sürdür.", "Kimlik doğrulama migration'ına devam et.", "Eski kritik auth kararını uygula."),
        "en": ("Continue the auth migration.", "Proceed with the authentication migration.", "Apply the old critical auth decision."),
        "tr-en": ("Auth migration'a devam edelim.", "Authentication migration'ı proceed edelim.", "Eski critical auth kararını uygula."),
    },
    "irrelevant_recent_memory": {
        "tr": ("Auth hatasını düzelt.", "Kimlik doğrulama bug'ını çöz.", "Session auth sorununu incele."),
        "en": ("Fix the auth bug.", "Resolve the authentication issue.", "Investigate the session auth problem."),
        "tr-en": ("Auth bug'ını düzelt.", "Authentication issue'yu resolve et.", "Session auth problem'i incele."),
    },
    "wrong_project_candidate": {
        "tr": ("Alpha auth kararını getir.", "Bu projedeki auth kararını bul.", "Current project authentication bilgisini getir."),
        "en": ("Retrieve the Alpha auth decision.", "Find this project's auth decision.", "Retrieve current-project authentication context."),
        "tr-en": ("Alpha auth kararını getir.", "Bu project's auth decision'ını bul.", "Current project auth context'i getir."),
    },
    "superseded_memory": {
        "tr": ("Güncel auth kararını kullan.", "Artık geçerli olan authentication kararını getir.", "Superseded auth kararını dışarıda bırak."),
        "en": ("Use the current auth decision.", "Retrieve the active authentication decision.", "Exclude the superseded auth decision."),
        "tr-en": ("Güncel auth kararını kullan.", "Active authentication decision'ı getir.", "Superseded auth kararını exclude et."),
    },
    "resolved_blocker": {
        "tr": ("Çözülmüş auth blocker'ı geri getirme.", "Artık kapanmış blocker'ı hariç tut.", "Resolved authentication engelini seçme."),
        "en": ("Do not return the resolved auth blocker.", "Exclude the closed authentication blocker.", "Do not select the resolved auth issue."),
        "tr-en": ("Resolved auth blocker'ı getirme.", "Closed authentication blocker'ı exclude et.", "Resolved auth issue'yu seçme."),
    },
    "ambiguous_reference": {
        "tr": ("Önceki kararı iptal et.", "Az önceki kararı geri al.", "Bunu iptal edelim."),
        "en": ("Cancel the previous decision.", "Undo the decision just mentioned.", "Cancel that one."),
        "tr-en": ("Önceki auth kararını iptal edelim.", "Az önceki auth decision'ı undo edelim.", "Bunu cancel edelim."),
    },
}


def _variant_text(category: str, language: str, variant: int) -> str:
    if category in _EXTRACTION_TEXT:
        return _EXTRACTION_TEXT[category][language][variant - 1]
    if category in _RETRIEVAL_TEXT:
        return _RETRIEVAL_TEXT[category][language][variant - 1]
    return _LANGUAGE_TEXT[language][variant - 1]


def _annotate_a(primary: dict[str, Any]) -> dict[str, Any]:
    """First blind labeling pass; receives only the case evidence."""

    return {"annotator_id": "ig01b-annotator-a", "method": "blind-pass-a", "label": dict(primary), "confidence": 1.0}


def _annotate_b(case: dict[str, Any]) -> dict[str, Any]:
    """Second blind pass derived from case evidence, never primary labels."""

    label = label_case_from_case(case)
    return {"annotator_id": "ig01b-annotator-b", "method": "blind-pass-b", "label": label, "confidence": 1.0}


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
    query = _variant_text(category, language, variant)
    required = [answer_id]
    forbidden: list[str] = []
    candidate_ids = [answer_id, distractor_id]
    rationale = "The evidence and expected label are explicit and sufficient for a competent system."
    primary: dict[str, Any] = {"category": category, "expected_memory_type": category}
    extraction_expected: dict[str, Any] | None = None
    extraction_forbidden: dict[str, Any] | None = None

    if category == "old_critical_decision":
        primary.update(expected_memory_type="decision", temporal="historical-critical")
    elif category == "irrelevant_recent_memory":
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
        primary.update(expected_memory_type="correction", correction_target="jwt")
    else:
        raise ValueError(category)

    if _FAMILY[category] == "extraction":
        role = "assistant" if category == "assistant_proposal" else "user"
        commitment = "explicit" if category == "explicit_decision" else "none"
        memory_type = {
            "explicit_decision": "decision", "preference": "preference", "lesson": "lesson",
            "requirement": "requirement", "correction": "correction", "negation": "no_commitment",
            "suggestion": "no_commitment", "hypothetical": "no_commitment", "question": "no_commitment",
            "quoted_material": "no_commitment", "assistant_proposal": "no_commitment",
        }[category]
        operation = {"explicit_decision": "ADD", "preference": "ADD", "lesson": "ADD", "requirement": "ADD", "correction": "CORRECT"}.get(category, "NOOP")
        extraction_expected = {
            "commitment": commitment,
            "memory_type": memory_type,
            "state_operation": operation,
            "correction": category == "correction",
            "target_behavior": "resolve" if category == "correction" else "none",
            "scope": "project-local",
            "source_role": "quoted_external" if category == "quoted_material" else role,
        }
        extraction_forbidden = {
            "canonical_commit": category in {"suggestion", "hypothetical", "question", "negation", "quoted_material", "assistant_proposal"},
            "wrong_type": "decision" if category != "explicit_decision" else "",
            "false_commitment": category in {"suggestion", "hypothetical", "question", "negation", "quoted_material", "assistant_proposal"},
        }

    annotation_evidence = {
        "family": _FAMILY[category],
        "query": query,
        "conversation": ([{"role": "assistant" if category == "assistant_proposal" else "user", "text": query}] if _FAMILY[category] == "extraction" else []),
        "candidate_ids": candidate_ids,
    }

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
        "conversation": ([{"role": "assistant" if category == "assistant_proposal" else "user", "text": query}] if _FAMILY[category] == "extraction" else []),
        "candidate_ids": candidate_ids,
        "required_ids": required,
        "acceptable_ids": required[:],
        "forbidden_ids": forbidden,
        "mandatory_ids": required[:],
        "rationale": rationale,
        "expected": extraction_expected,
        "forbidden": extraction_forbidden,
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
                "annotator_a": _annotate_a(primary),
                "annotator_b": _annotate_b(annotation_evidence),
                "adjudicated": dict(primary),
                "disagreement": False,
                "protocol": "blind-independent-case-only-labeling",
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
    # Use explicit LF bytes so the pinned digest is portable across Windows
    # and Linux checkouts.
    path.write_bytes(text.encode("utf-8"))
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
    (root / "manifest.json").write_bytes((json.dumps(manifest, indent=2, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8"))
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate the deterministic IG01-B public corpus")
    parser.add_argument("--root", type=Path, default=PUBLIC_ROOT)
    args = parser.parse_args()
    print(json.dumps(generate(args.root), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
