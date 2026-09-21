"""Scope-safe, query-blind recency continuity evaluation provider."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

from brain_eleven.memory import MemoryStore, filter_memories
from brain_eleven.state.resolver import STATE_AVAILABLE, StateResolver
from context_compiler_v2.tokenizer import ConservativeTokenEstimator

from ..contracts import NormalizedEvaluationResult, SelectedContextItem
from ..schema import GoldenTask


RECENCY_PROVIDER_ID = "recency_continuity"
DEFAULT_MAX_CONTEXT_TOKENS = 2048
DEFAULT_MINIMUM_HEADROOM_TOKENS = 128
DEFAULT_HARD_BYTE_LIMIT = 24_000

RECENCY_CAPABILITIES = {
    "scope_isolation": "supported",
    "lifecycle_filtering": "supported",
    "task_aware_ranking": "unsupported",
    "authority_resolution": "supported",
    "conflict_resolution": "supported",
    "token_budgeting": "supported",
}


class RecencyProviderError(RuntimeError):
    """Raised when canonical inputs cannot satisfy the frozen provider contract."""


def _timestamp(value: object) -> datetime:
    if not isinstance(value, str) or not value.strip():
        return datetime.min.replace(tzinfo=timezone.utc)
    normalized = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as error:
        raise RecencyProviderError("candidate timestamp is invalid") from error
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)


def _memory_id(record: Mapping[str, Any]) -> str:
    value = record.get("memory_id", record.get("id"))
    if not isinstance(value, str) or not value.strip():
        raise RecencyProviderError("canonical memory is missing its id")
    return value.strip()


def _render_item(item: SelectedContextItem) -> str:
    return (
        f"[{item.source_type}:{item.id}]\n"
        f"type={item.memory_type}\nstatus={item.status}\n{item.content}\n"
    )


def _open_state_items(state: Any) -> Iterable[Mapping[str, Any]]:
    if state is None or state.status != STATE_AVAILABLE:
        return ()
    result: list[Mapping[str, Any]] = []
    for source_type, attribute in (
        ("state_requirement", "active_requirements"),
        ("state_blocker", "active_blockers"),
    ):
        records = getattr(state, attribute, ())
        for record in records if isinstance(records, (list, tuple)) else ():
            if isinstance(record, Mapping):
                result.append({**record, "_source_type": source_type})
    return result


class RecencyContinuityProvider:
    """Read canonical state/memory and select newest safe items without task text."""

    provider_id = RECENCY_PROVIDER_ID

    def __init__(
        self,
        *,
        max_context_tokens: int = DEFAULT_MAX_CONTEXT_TOKENS,
        minimum_headroom_tokens: int = DEFAULT_MINIMUM_HEADROOM_TOKENS,
        hard_byte_limit: int = DEFAULT_HARD_BYTE_LIMIT,
    ) -> None:
        if minimum_headroom_tokens >= max_context_tokens:
            raise ValueError("minimum headroom must be below max context tokens")
        self.usable_tokens = max_context_tokens - minimum_headroom_tokens
        self.hard_byte_limit = hard_byte_limit
        self.estimator = ConservativeTokenEstimator()

    def _candidate_items(self, task: GoldenTask, vault: Path) -> tuple[SelectedContextItem, ...]:
        state = StateResolver(vault).resolve(task.project_id) if task.project_id else None
        state_records = list(_open_state_items(state))
        state_records.sort(key=lambda item: str(item.get("id", "")))
        state_records.sort(key=lambda item: _timestamp(item.get("updated_at")), reverse=True)
        items: list[SelectedContextItem] = []
        for record in state_records:
            record_id = record.get("id")
            content = record.get("text", record.get("description", record.get("title")))
            if not isinstance(record_id, str) or not isinstance(content, str) or not content.strip():
                raise RecencyProviderError("open state item is malformed")
            items.append(
                SelectedContextItem(
                    id=record_id,
                    source_type=str(record["_source_type"]),
                    project_id=task.project_id,
                    memory_type="requirement" if record["_source_type"] == "state_requirement" else "blocker",
                    status="open",
                    content=content,
                    score=0.0,
                )
            )

        document = MemoryStore(vault).load()
        scoped = filter_memories(
            (item for item in document.get("validated_memory", ()) if isinstance(item, Mapping)),
            project_id=task.project_id,
            retrieval_scope="default",
        )
        active = [item for item in scoped if str(item.get("status", "active")).lower() == "active"]
        active.sort(key=_memory_id)
        active.sort(
            key=lambda item: _timestamp(item.get("created_at", item.get("timestamp"))),
            reverse=True,
        )
        active.sort(
            key=lambda item: _timestamp(item.get("updated_at", item.get("timestamp"))),
            reverse=True,
        )
        for record in active:
            content = record.get("content")
            if not isinstance(content, str) or not content.strip():
                raise RecencyProviderError("canonical memory content is malformed")
            project_id = record.get("project_id") or None
            items.append(
                SelectedContextItem(
                    id=_memory_id(record),
                    source_type="memory",
                    project_id=project_id if isinstance(project_id, str) else None,
                    memory_type=str(record.get("type", "observation")),
                    status="active",
                    content=content,
                    score=0.0,
                )
            )
        return tuple(items)

    def select(self, task: GoldenTask, vault_path: Path | str) -> NormalizedEvaluationResult:
        vault = Path(vault_path)
        if not vault.is_dir():
            raise RecencyProviderError(f"evaluation vault must be a directory: {vault}")
        selected: list[SelectedContextItem] = []
        rendered = ""
        for item in self._candidate_items(task, vault):
            candidate = rendered + _render_item(item)
            estimate = self.estimator.estimate(candidate)
            if estimate.count > self.usable_tokens or estimate.byte_count > self.hard_byte_limit:
                break
            selected.append(item)
            rendered = candidate
        revision = MemoryStore(vault).revision()
        return NormalizedEvaluationResult(
            task_id=task.task_id,
            provider_id=self.provider_id,
            selected_items=tuple(selected),
            source_memory_revision=revision,
            project_id=task.project_id,
            retrieval_scope="default",
            capabilities=RECENCY_CAPABILITIES,
        )
