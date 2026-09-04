"""Compact, structured and prompt-boundary-safe Context Compiler V2 rendering."""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable, Mapping

from .adapters import RehydratedCandidate
from .models import ContextItem, ContextSection, TokenEstimate
from .safety import escape_untrusted_text


SECTION_FOR_ROLE = {
    "TASK": "TASK",
    "CONSTRAINT": "REQUIREMENTS & CONSTRAINTS",
    "REQUIREMENT": "REQUIREMENTS & CONSTRAINTS",
    "CURRENT_STATE": "CURRENT STATE",
    "DECISION": "DECISIONS",
    "IMPLEMENTATION_GAP": "KNOWN GAPS / CONFLICTS",
    "CONFLICT": "KNOWN GAPS / CONFLICTS",
    "LESSON": "RELEVANT LESSONS",
    "PREFERENCE": "RELEVANT LESSONS",
    "OPEN_LOOP": "RELEVANT LESSONS",
    "HISTORICAL_CONTEXT": "OPTIONAL SUPPORT",
    "IMPLEMENTATION_FACT": "CRITICAL CONTEXT",
    "SUPPORTING_EVIDENCE": "OPTIONAL SUPPORT",
}
SECTION_ORDER = (
    "TASK",
    "CRITICAL CONTEXT",
    "CURRENT STATE",
    "DECISIONS",
    "REQUIREMENTS & CONSTRAINTS",
    "KNOWN GAPS / CONFLICTS",
    "RELEVANT LESSONS",
    "OPTIONAL SUPPORT",
)


def render_fragment(item: RehydratedCandidate, role: str) -> str:
    """Preserve source wording while binding it as untrusted data, not instructions."""
    label = role.replace("_", " ")
    status = item.resolution.status.replace("_", " ")
    text = escape_untrusted_text(item.text).replace("\r\n", "\n").strip()
    return f"- [{label}; {status}; {item.resolution.candidate_id}] {text}"


def render_task(task_state: Any) -> str:
    task = task_state.task
    project = task.project.project_id or "unresolved"
    intent = task.intent.value
    raw = escape_untrusted_text(task.raw_request).replace("\r\n", "\n").strip()
    return f"Project: {project}\nIntent: {intent}\nGoal: {raw}"


def build_sections(items: Iterable[ContextItem]) -> tuple[ContextSection, ...]:
    grouped: dict[str, list[str]] = defaultdict(list)
    for item in items:
        grouped[SECTION_FOR_ROLE[item.role]].append(item.candidate_id)
    return tuple(
        ContextSection(name, tuple(grouped[name]))
        for name in SECTION_ORDER
        if grouped.get(name)
    )


def render_bundle(task_state: Any, items: Iterable[ContextItem]) -> str:
    selected = tuple(items)
    by_section: dict[str, list[ContextItem]] = defaultdict(list)
    for item in selected:
        by_section[SECTION_FOR_ROLE[item.role]].append(item)
    lines = ["[BRAIN-ELEVEN TASK CONTEXT v2]", "", "TASK", render_task(task_state)]
    for name in SECTION_ORDER:
        records = by_section.get(name)
        if not records:
            continue
        lines.extend(("", name))
        lines.extend(item.rendered_text for item in sorted(records, key=lambda value: (value.tier, value.candidate_id)))
    lines.extend(("", "[END BRAIN-ELEVEN CONTEXT]"))
    return "\n".join(lines)


def context_item_from_draft(draft: Any, reason: str, estimate: TokenEstimate) -> ContextItem:
    return ContextItem(
        candidate_id=draft.evidence.resolution.candidate_id,
        source_type=draft.evidence.resolution.source_type,
        project_id=draft.evidence.project_id,
        canonical_ref=draft.evidence.resolution.canonical_ref,
        role=draft.role,
        tier=draft.tier,
        epistemic_status=draft.evidence.resolution.status,
        compression_mode="FULL",
        selection_reason=reason,
        rendered_text=draft.rendered_text,
        token_estimate=estimate,
    )
