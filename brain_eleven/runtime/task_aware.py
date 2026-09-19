"""Bounded, deterministic W-06B task-aware V1 selection.

This module deliberately consumes the legacy compiler's canonical, already
scoped memory projection.  It does not call V2, write authorities, or retain
the raw prompt.
"""
from dataclasses import dataclass
import hashlib
import re
from typing import Any

from context_compiler_v2.safety import contains_secret
from context_compiler_v2.tokenizer import ConservativeTokenEstimator
from brain_eleven.memory.scope import infer_memory_scope
from .capture_safety import evaluate_capture

INTENTS = frozenset({"IMPLEMENT", "MIGRATE", "TEST", "DEBUG", "REVIEW", "PLAN", "DESIGN", "RESEARCH", "GENERAL"})
STATUSES = frozenset({"READY", "NO_NEED", "AMBIGUOUS", "UNAVAILABLE", "INVALID"})
MAX_ITEMS, MAX_TOKENS, MAX_BYTES = 5, 1024, 8192
_WORD = re.compile(r"[^\W_]+", re.UNICODE)


@dataclass(frozen=True)
class TaskNeedInput:
    task_id: str
    project_id: str | None
    intent: str
    continuation: bool
    entities: tuple[str, ...]
    needs: tuple[str, ...]
    raw_prompt: str = ""
    schema_version: int = 1


@dataclass(frozen=True)
class TaskNeedResult:
    status: str
    profile: str | None
    needs: tuple[str, ...]
    project_id: str | None
    error_code: str | None = None
    schema_version: int = 1

    def to_dict(self) -> dict[str, Any]:
        return {"status": self.status, "profile": self.profile, "needs": list(self.needs),
                "project_id": self.project_id, "error_code": self.error_code,
                "schema_version": self.schema_version}


def task_need(task: Any) -> tuple[TaskNeedInput, TaskNeedResult]:
    project = getattr(getattr(task, "project", None), "project_id", None)
    intent = getattr(getattr(task, "intent", None), "value", getattr(task, "intent", "GENERAL"))
    intent = intent if intent in INTENTS else "GENERAL"
    entities = tuple(sorted(set(str(x).strip() for x in getattr(task, "entities", ()) if str(x).strip())))[:32]
    needs = tuple(sorted(set(str(x).strip() for x in getattr(task, "context_needs", ()) if str(x).strip())))[:16]
    raw = str(getattr(task, "raw_request", ""))
    item = TaskNeedInput(str(getattr(task, "task_id", "")), project, intent,
                        bool(getattr(task, "continuation_of", None)), entities, needs, raw)
    if not item.task_id or len(item.task_id) > 256 or (project is not None and len(project) > 256):
        return item, TaskNeedResult("INVALID", None, (), project, "INVALID")
    if intent == "GENERAL" and not entities and not needs:
        return item, TaskNeedResult("NO_NEED", "general", (), project)
    profile = "continuation" if item.continuation else intent.lower()
    return item, TaskNeedResult("READY", profile, needs, project)


def _scope_is_eligible(memory: dict[str, Any], project_id: str | None) -> bool:
    """Apply the canonical global/project scope rule to a ranked record."""
    scope, _, memory_project_id = infer_memory_scope(memory)
    return scope == "global" or (scope == "project" and memory_project_id == project_id)


def select(compiler: Any, task: Any, *, budget: int = 1024, human_approval: bool = False) -> dict[str, Any]:
    """Rerank already eligible V1 records and render within hard bounds."""
    need, result = task_need(task)
    if result.status != "READY":
        return {"status": result.status, "task_need": result.to_dict(), "selected": [], "context": "", "provider": "V1"}
    try:
        safe = lambda text: not contains_secret(text) and evaluate_capture(text).accepted
        records = [x for x in compiler._rank_memories(limit=MAX_ITEMS * 8)
                   if _scope_is_eligible(x, result.project_id) and safe(x.get("content", ""))
                   and (not human_approval or x.get("is_approved", True) is True)]
        terms = set(_WORD.findall((need.raw_prompt + " " + " ".join(need.entities) + " " + " ".join(need.needs)).casefold()))
        def key(item):
            words = set(_WORD.findall(str(item.get("content", "")).casefold()))
            lexical = len(words & terms) / max(1, len(terms))
            fingerprint = hashlib.sha256(str(item.get("content", "")).encode("utf-8")).hexdigest()
            return (-lexical, -float(item.get("ranking_score", 0)), str(item.get("type", "")),
                    str(item.get("id", item.get("memory_id", ""))), fingerprint)
        records.sort(key=key)
        selected = []
        estimator = ConservativeTokenEstimator()
        state = compiler._resolve_current_state()
        for item in records:
            if len(selected) >= MAX_ITEMS:
                break
            trial = selected + [item]
            context = compiler._generate_context_block(trial, {}, "", "", state)
            if estimator.estimate(context).count > min(MAX_TOKENS, budget) or len(context.encode("utf-8")) > MAX_BYTES:
                continue
            selected = trial
        context = compiler._generate_context_block(selected, {}, "", "", state) if selected else ""
        return {"status": "SUCCESS" if context else "EMPTY", "task_need": result.to_dict(), "selected": selected,
                "selected_ids": [x.get("memory_id", x.get("id")) for x in selected], "context": context,
                "provider": "W06B_TASK_AWARE", "estimated_tokens": estimator.estimate(context).count}
    except Exception:
        return {"status": "UNAVAILABLE", "task_need": result.to_dict(), "selected": [], "context": "", "provider": "V1",
                "error_code": "RETRIEVAL_MODE_UNAVAILABLE"}
