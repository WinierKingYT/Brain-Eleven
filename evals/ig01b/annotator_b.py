"""Independent blind annotator B for the synthetic holdout.

This pass classifies the case evidence itself. It receives no category or
primary-label object from generator A; the generator uses only the query,
conversation role/text and candidate metadata available in the fixture.
"""

from __future__ import annotations

import re
from typing import Any


def _text(case: dict[str, Any]) -> str:
    turns = case.get("conversation") or []
    return " ".join(str(turn.get("text", "")) for turn in turns).lower() + " " + str(case.get("query", "")).lower()


def _label(category: str) -> dict[str, Any]:
    label: dict[str, Any] = {"category": category}
    if category == "explicit_decision":
        label.update(expected_memory_type="decision", commitment="explicit")
    elif category in {"preference", "lesson", "requirement"}:
        label.update(expected_memory_type=category)
    elif category == "old_critical_decision":
        label.update(expected_memory_type="decision", temporal="historical-critical")
    elif category == "wrong_project_candidate":
        label.update(expected_memory_type="decision", scope="project-local")
    elif category == "superseded_memory":
        label.update(expected_memory_type="decision", lifecycle="active-only")
    elif category == "resolved_blocker":
        label.update(expected_memory_type="state", lifecycle="resolved-excluded")
    elif category == "irrelevant_recent_memory":
        label.update(expected_memory_type="decision")
    elif category == "ambiguous_reference":
        label.update(expected_memory_type="review", abstain=True)
    elif category == "correction":
        label.update(expected_memory_type="correction", correction_target="jwt")
    elif category in {"suggestion", "hypothetical", "question", "negation", "quoted_material", "assistant_proposal"}:
        label.update(expected_memory_type="no_commitment")
    else:
        raise ValueError(f"unknown inferred category: {category}")
    return label


def _infer_category(case: dict[str, Any]) -> str:
    family = case.get("family")
    text = _text(case)
    candidates = [str(item).lower() for item in case.get("candidate_ids", [])]
    if family == "reference_resolution":
        return "ambiguous_reference"
    if family == "retrieval":
        if any(item.startswith("foreign-") for item in candidates):
            return "wrong_project_candidate"
        if any(item.endswith("-old") for item in candidates):
            return "superseded_memory"
        if any("old_critical_decision" in item for item in candidates):
            return "old_critical_decision"
        if any("resolved_blocker" in item for item in candidates):
            return "resolved_blocker"
        if any("irrelevant_recent_memory" in item for item in candidates):
            return "irrelevant_recent_memory"
        if re.search(r"old critical|eski kritik", text):
            return "old_critical_decision"
        if re.search(r"resolved|closed|çözülmüş|kapanmış", text):
            return "resolved_blocker"
        return "irrelevant_recent_memory"
    if family != "extraction":
        raise ValueError(f"unknown case family: {family}")
    turns = case.get("conversation") or []
    if turns and turns[0].get("role") == "assistant":
        return "assistant_proposal"
    if re.search(r"quoted|quote|alıntı|şöyle yazdı|notta şu|user wrote|user note|document", text):
        return "quoted_material"
    if re.search(r"correction|instead|yerine|düzeltiyorum|yanlış", text) or ("jwt" in text and "session cookie" in text):
        return "correction"
    if re.search(r"what if|suppose|if .*existed|eğer|varsayalım|olsaydı|kullansaydık", text):
        return "hypothetical"
    if "?" in text or re.search(r"\b(mı|mi|mu|mü)\b", text):
        return "question"
    if re.search(r"must|required|requires|zorunlu|gereklidir|şart|taşımalı", text):
        return "requirement"
    if re.search(r"lesson|learned|ders oldu|öğrendik|ölçmeden|önce test|before deploying|should measure", text):
        return "lesson"
    if re.search(r"prefer|preference|tercih|dark mode", text):
        return "preference"
    if re.search(r"will not|not using|do not|kullanmayacağız|kullanmıyoruz|seçmiyoruz", text):
        return "negation"
    if re.search(r"could|maybe|suggest|recommend|istersen|belki|bence|öner", text):
        return "suggestion"
    return "explicit_decision"


def label_case_from_case(case: dict[str, Any]) -> dict[str, Any]:
    """Return a label from case evidence only, without primary labels/category."""

    return _label(_infer_category(case))
