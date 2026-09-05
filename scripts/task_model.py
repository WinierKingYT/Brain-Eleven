#!/usr/bin/env python3
"""Canonical runtime contract for one Brain-Eleven task invocation.

Task envelopes deliberately describe an invocation without persisting it or
selecting memories.  A future router may consume this stable JSON contract.
"""

from __future__ import annotations

import json
import re
import secrets
import time
import argparse
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from brain_eleven.projects.registry import ProjectRegistry, ProjectRegistryError


TASK_SCHEMA_VERSION = 1
TASK_ID_PREFIX = "tsk_"
TASK_LIFECYCLES = frozenset({"RECEIVED", "ANALYZED"})
PROJECT_RESOLUTION_STATUSES = frozenset({"resolved", "unresolved", "archived"})
INTENTS = frozenset(
    {
        "IMPLEMENT",
        "DEBUG",
        "REVIEW",
        "PLAN",
        "RESEARCH",
        "EXPLAIN",
        "DESIGN",
        "MIGRATE",
        "TEST",
        "OPERATE",
        "UNKNOWN",
    }
)
OPERATIONS = frozenset({"design", "inspect", "modify", "test", "operate", "unknown"})
RISK_LEVELS = frozenset({"LOW", "MEDIUM", "HIGH", "CRITICAL"})
REQUESTED_OUTPUTS = frozenset(
    {
        "implementation_plan",
        "design_spec",
        "code_change",
        "review_report",
        "research_notes",
        "explanation",
        "test_result",
        "operational_result",
        "unknown",
    }
)
EVIDENCE_SOURCES = frozenset({"user", "project_registry", "task_analyzer", "system"})
MAX_REQUEST_CHARS = 100_000
_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


class TaskValidationError(ValueError):
    """Raised when an untrusted task envelope does not meet the contract."""


class TaskProjectResolutionError(RuntimeError):
    """Raised when the project registry cannot safely answer a task lookup."""


@dataclass(frozen=True)
class _Rule:
    value: str
    phrases: tuple[str, ...]


_INTENT_RULES = (
    _Rule("PLAN", ("planla", "planını", "planini", "plan yap", "roadmap", "yol haritası", "plan")),
    _Rule("REVIEW", ("code review", "review", "inspect", "incele", "gözden geçir", "audit", "denetle")),
    _Rule("DEBUG", ("debug", "bug", "hata", "fix", "düzelt", "arıza")),
    _Rule("MIGRATE", ("migrate", "migration", "migrasyon", "göç")),
    _Rule("TEST", ("test et", "test", "doğrula", "validate")),
    _Rule("RESEARCH", ("araştır", "research", "investigate", "keşfet")),
    _Rule("EXPLAIN", ("açıkla", "explain", "nasıl çalış")),
    _Rule("DESIGN", ("tasarla", "design", "mimari", "architecture")),
    _Rule("OPERATE", ("deploy", "çalıştır", "operate", "izle", "monitor", "release")),
    _Rule("IMPLEMENT", ("uygula", "implement", "ekle", "oluştur", "build", "yap")),
)

_DOMAIN_RULES = (
    _Rule("context-engine", ("context engine", "context", "bağlam", "router", "retrieval")),
    _Rule("task-model", ("task model", "task", "görev")),
    _Rule("state-management", ("state", "project state", "durum")),
    _Rule("memory", ("memory", "hafıza", "validated-memory", "memory store")),
    _Rule("project-identity", ("project registry", "project identity", "proje kaydı")),
    _Rule("session-runtime", ("sessionstart", "sessionend", "bootstrap", "hook", "oturum")),
    _Rule("evaluation", ("evaluation", "eval", "benchmark", "golden corpus")),
    _Rule("recovery", ("backup", "restore", "recovery", "yedek", "geri yükle")),
    _Rule("security", ("security", "secret", "token", "api key", "güvenlik", "parola")),
    _Rule("persistence", ("sqlite", "json", "store", "migration", "migrasyon", "göç")),
)

_EXPLICIT_CONSTRAINT_RULES = (
    _Rule("no_production_changes", ("production code'a dokunma", "production code dokunma", "production değiştir", "productiona dokunma")),
    _Rule("no_router", ("router yapma", "router ekleme", "no router")),
    _Rule("no_llm", ("llm kullanma", "model kullanma", "no llm")),
    _Rule("offline_only", ("internet kullanma", "network kullanma", "offline")),
    _Rule("no_commit_or_push", ("commit yapma", "push yapma", "no commit", "no push")),
)

_RISK_RULES = (
    _Rule("data_loss", ("rm -rf", "hard reset", "veri kaybı", "data loss")),
    _Rule("destructive_change", ("sil", "silme", "silmeyi", "delete", "drop", "overwrite", "üzerine yaz")),
    _Rule("migration", ("migration", "migrasyon", "göç", "schema")),
    _Rule("security", ("auth", "secret", "token", "api key", "password", "parola")),
    _Rule("canonical_store", ("validated-memory", "memory store", "canonical memory", "canonical store")),
    _Rule("architecture_change", ("architecture", "mimari", "contract", "sözleşme", "tasarla", "design")),
    _Rule("cross_project", ("cross-project", "başka proje", "other project", "projects")),
    _Rule("external_dependency", ("network", "internet", "external", "deploy", "deployment", "docker")),
)

_INTENT_OPERATION = {
    "PLAN": "design",
    "DESIGN": "design",
    "REVIEW": "inspect",
    "RESEARCH": "inspect",
    "EXPLAIN": "inspect",
    "DEBUG": "modify",
    "IMPLEMENT": "modify",
    "MIGRATE": "modify",
    "TEST": "test",
    "OPERATE": "operate",
    "UNKNOWN": "unknown",
}

_INTENT_OUTPUT = {
    "PLAN": "implementation_plan",
    "DESIGN": "design_spec",
    "REVIEW": "review_report",
    "RESEARCH": "research_notes",
    "EXPLAIN": "explanation",
    "DEBUG": "code_change",
    "IMPLEMENT": "code_change",
    "MIGRATE": "code_change",
    "TEST": "test_result",
    "OPERATE": "operational_result",
    "UNKNOWN": "unknown",
}


def utc_now() -> str:
    """Return a portable UTC timestamp for envelope creation."""
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _encode_crockford(value: int, length: int) -> str:
    encoded = []
    for _ in range(length):
        encoded.append(_CROCKFORD[value & 31])
        value >>= 5
    return "".join(reversed(encoded))


def new_task_id() -> str:
    """Create a task-scoped ULID-shaped immutable identifier without I/O."""
    timestamp = int(time.time() * 1000)
    random_bits = int.from_bytes(secrets.token_bytes(10), "big")
    return TASK_ID_PREFIX + _encode_crockford(timestamp, 10) + _encode_crockford(random_bits, 16)


def resolve_project(
    vault_path: str | Path,
    project_root: str | Path,
) -> "ProjectResolution":
    """Resolve an existing project identity without ever registering one."""
    try:
        record = ProjectRegistry(vault_path).resolve(project_root)
    except ProjectRegistryError as exc:
        raise TaskProjectResolutionError("Project registry is unavailable for task resolution") from exc
    if record is None:
        return ProjectResolution(
            project_id=None,
            status="unresolved",
            source="project_registry",
            confidence=0.0,
        )
    status = "archived" if record["status"] == "archived" else "resolved"
    return ProjectResolution(
        project_id=record["project_id"],
        status=status,
        source="project_registry",
        confidence=1.0,
    )


def _normalized_request(raw_request: str) -> str:
    return " ".join(raw_request.casefold().split())


def _matches_phrase(request: str, phrase: str) -> bool:
    """Match a configured phrase as text, never as a substring of another word."""
    return re.search(rf"(?<!\w){re.escape(phrase)}(?!\w)", request) is not None


def _first_rule_value(request: str, rules: Sequence[_Rule], fallback: str) -> str:
    return next(
        (rule.value for rule in rules if any(_matches_phrase(request, phrase) for phrase in rule.phrases)),
        fallback,
    )


def _all_rule_values(request: str, rules: Sequence[_Rule]) -> tuple[str, ...]:
    return tuple(
        rule.value
        for rule in rules
        if any(_matches_phrase(request, phrase) for phrase in rule.phrases)
    )


def _extract_entities(raw_request: str) -> tuple[str, ...]:
    """Keep only exact user-provided identifiers; never infer entities."""
    found: list[str] = []
    for match in re.finditer(r"\bphase[- ]\d+\b", raw_request, flags=re.IGNORECASE):
        value = match.group(0).casefold().replace(" ", "-")
        if value not in found:
            found.append(value)
    for match in re.finditer(r"\b(?:[A-Z][A-Za-z0-9_]{2,}|[a-z]+_[a-z0-9_]+)\b", raw_request):
        value = match.group(0)
        if value.casefold() == "phase":
            continue
        if value not in found:
            found.append(value)
    return tuple(found)


def _risk_level(flags: tuple[str, ...]) -> str:
    if "data_loss" in flags or ({"destructive_change", "canonical_store"} <= set(flags)):
        return "CRITICAL"
    if {"destructive_change", "migration", "security", "canonical_store"} & set(flags):
        return "HIGH"
    if flags:
        return "MEDIUM"
    return "LOW"


def _context_needs(intent: str, project: "ProjectResolution") -> tuple[str, ...]:
    needs: list[str] = []
    if project.project_id is not None:
        needs.append("current_project_state")
    if intent in {"PLAN", "DESIGN", "IMPLEMENT", "DEBUG", "MIGRATE"}:
        needs.extend(("project_decisions", "active_requirements"))
    elif intent in {"REVIEW", "TEST"}:
        needs.extend(("project_decisions", "recent_changes"))
    elif intent == "RESEARCH":
        needs.append("relevant_lessons")
    return tuple(dict.fromkeys(needs))


class TaskAnalyzer:
    """Deterministic, offline interpretation of one raw request."""

    def __init__(self, vault_path: str | Path, project_root: str | Path):
        self.vault_path = Path(vault_path)
        self.project_root = Path(project_root)

    def analyze(
        self,
        raw_request: str,
        *,
        task_id: Optional[str] = None,
        created_at: Optional[str] = None,
        parent_task_id: Optional[str] = None,
        continuation_of: Optional[str] = None,
    ) -> "TaskEnvelope":
        raw_request = _require_string(raw_request, "request.raw", allow_empty=True)
        if not raw_request.strip():
            raise TaskValidationError("request.raw must not be blank")
        if len(raw_request) > MAX_REQUEST_CHARS:
            raise TaskValidationError(f"request.raw exceeds {MAX_REQUEST_CHARS} characters")

        project = resolve_project(self.vault_path, self.project_root)
        normalized = _normalized_request(raw_request)
        intent = _first_rule_value(normalized, _INTENT_RULES, "UNKNOWN")
        domains = _all_rule_values(normalized, _DOMAIN_RULES)
        explicit_constraints = _all_rule_values(normalized, _EXPLICIT_CONSTRAINT_RULES)
        risk_flags = _all_rule_values(normalized, _RISK_RULES)
        risk = _risk_level(risk_flags)
        intent_confidence = 0.95 if intent != "UNKNOWN" else 0.0
        domain_confidence = 0.80 if domains else 0.0
        overall = round((project.confidence + intent_confidence + domain_confidence) / 3, 4)
        ambiguities: list[str] = []
        if project.status == "unresolved":
            ambiguities.append("project")
        if intent == "UNKNOWN":
            ambiguities.append("intent")
        if not domains:
            ambiguities.append("domain")

        envelope = TaskEnvelope(
            task_id=task_id or new_task_id(),
            created_at=created_at or utc_now(),
            lifecycle="ANALYZED",
            project=project,
            raw_request=raw_request,
            intent=Evidence(intent, "task_analyzer", intent_confidence),
            operation=Evidence(_INTENT_OPERATION[intent], "task_analyzer", intent_confidence),
            requested_output=Evidence(_INTENT_OUTPUT[intent], "task_analyzer", intent_confidence),
            explicit_constraints=explicit_constraints,
            inherited_constraints=(),
            entities=_extract_entities(raw_request),
            canonical_domains=domains,
            discovered_domains=(),
            risk_level=Evidence(risk, "task_analyzer", 0.95 if risk_flags else 0.60),
            risk_flags=risk_flags,
            context_needs=_context_needs(intent, project),
            ambiguities=tuple(ambiguities),
            confidence={
                "overall": overall,
                "project": project.confidence,
                "intent": intent_confidence,
                "domains": domain_confidence,
            },
            parent_task_id=parent_task_id,
            continuation_of=continuation_of,
        )
        return TaskEnvelope.from_dict(envelope.to_dict())


def _require_string(value: Any, field: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str):
        raise TaskValidationError(f"{field} must be a string")
    if not allow_empty and not value.strip():
        raise TaskValidationError(f"{field} must not be empty")
    return value


def _require_confidence(value: Any, field: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise TaskValidationError(f"{field} must be a number")
    confidence = float(value)
    if not 0.0 <= confidence <= 1.0:
        raise TaskValidationError(f"{field} must be between 0 and 1")
    return confidence


def _require_string_tuple(value: Any, field: str) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        raise TaskValidationError(f"{field} must be an array")
    result = tuple(_require_string(item, f"{field}[{index}]").strip() for index, item in enumerate(value))
    if len(result) != len(set(result)):
        raise TaskValidationError(f"{field} must not contain duplicates")
    return result


def _mapping(value: Any, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TaskValidationError(f"{field} must be an object")
    return value


def _exact_keys(
    value: Mapping[str, Any],
    field: str,
    required: set[str],
    optional: set[str] | frozenset[str] = frozenset(),
) -> None:
    missing = required - value.keys()
    unknown = value.keys() - required - optional
    if missing:
        raise TaskValidationError(f"{field} missing field(s): {', '.join(sorted(missing))}")
    if unknown:
        raise TaskValidationError(f"{field} has unknown field(s): {', '.join(sorted(unknown))}")


@dataclass(frozen=True)
class Evidence:
    """A normalized value with its explicit authority and confidence."""

    value: str
    source: str
    confidence: float

    @classmethod
    def from_dict(cls, document: Mapping[str, Any], field: str) -> "Evidence":
        document = _mapping(document, field)
        _exact_keys(document, field, {"value", "source", "confidence"})
        source = _require_string(document["source"], f"{field}.source").strip()
        if source not in EVIDENCE_SOURCES:
            raise TaskValidationError(f"{field}.source is unsupported: {source}")
        return cls(
            value=_require_string(document["value"], f"{field}.value").strip(),
            source=source,
            confidence=_require_confidence(document["confidence"], f"{field}.confidence"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {"value": self.value, "source": self.source, "confidence": self.confidence}


@dataclass(frozen=True)
class ProjectResolution:
    """Read-only project identity resolution for this task."""

    project_id: Optional[str]
    status: str
    source: str
    confidence: float

    @classmethod
    def from_dict(cls, document: Mapping[str, Any]) -> "ProjectResolution":
        document = _mapping(document, "project")
        _exact_keys(document, "project", {"project_id", "status", "source", "confidence"})
        status = _require_string(document["status"], "project.status").strip()
        if status not in PROJECT_RESOLUTION_STATUSES:
            raise TaskValidationError(f"project.status is unsupported: {status}")
        project_id = document["project_id"]
        if project_id is not None:
            project_id = _require_string(project_id, "project.project_id").strip()
        if status == "unresolved" and project_id is not None:
            raise TaskValidationError("unresolved project must not carry project_id")
        if status != "unresolved" and project_id is None:
            raise TaskValidationError("resolved or archived project requires project_id")
        source = _require_string(document["source"], "project.source").strip()
        if source not in EVIDENCE_SOURCES:
            raise TaskValidationError(f"project.source is unsupported: {source}")
        return cls(
            project_id=project_id,
            status=status,
            source=source,
            confidence=_require_confidence(document["confidence"], "project.confidence"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_id": self.project_id,
            "status": self.status,
            "source": self.source,
            "confidence": self.confidence,
        }


@dataclass(frozen=True)
class TaskEnvelope:
    """Immutable, schema-validated runtime representation of a user request."""

    task_id: str
    created_at: str
    lifecycle: str
    project: ProjectResolution
    raw_request: str
    intent: Evidence
    operation: Evidence
    requested_output: Evidence
    explicit_constraints: tuple[str, ...]
    inherited_constraints: tuple[str, ...]
    entities: tuple[str, ...]
    canonical_domains: tuple[str, ...]
    discovered_domains: tuple[str, ...]
    risk_level: Evidence
    risk_flags: tuple[str, ...]
    context_needs: tuple[str, ...]
    ambiguities: tuple[str, ...]
    confidence: Mapping[str, float]
    parent_task_id: Optional[str] = None
    continuation_of: Optional[str] = None

    @classmethod
    def from_dict(cls, document: Mapping[str, Any]) -> "TaskEnvelope":
        document = _mapping(document, "task")
        _exact_keys(
            document,
            "task",
            {
                "schema_version",
                "task_id",
                "created_at",
                "lifecycle",
                "project",
                "request",
                "intent",
                "operation",
                "requested_output",
                "constraints",
                "entities",
                "domains",
                "risk",
                "context_needs",
                "ambiguities",
                "confidence",
            },
            {"parent_task_id", "continuation_of"},
        )
        if document["schema_version"] != TASK_SCHEMA_VERSION:
            raise TaskValidationError(f"Unsupported task schema: {document['schema_version']}")
        task_id = _require_string(document["task_id"], "task.task_id").strip()
        if not task_id.startswith(TASK_ID_PREFIX):
            raise TaskValidationError("task.task_id must use tsk_ namespace")
        lifecycle = _require_string(document["lifecycle"], "task.lifecycle").strip()
        if lifecycle not in TASK_LIFECYCLES:
            raise TaskValidationError(f"task.lifecycle is unsupported: {lifecycle}")

        request = _mapping(document["request"], "task.request")
        _exact_keys(request, "task.request", {"raw"})
        raw_request = _require_string(request["raw"], "task.request.raw", allow_empty=True)
        if not raw_request.strip():
            raise TaskValidationError("task.request.raw must not be blank")
        if len(raw_request) > MAX_REQUEST_CHARS:
            raise TaskValidationError(f"task.request.raw exceeds {MAX_REQUEST_CHARS} characters")

        constraints = _mapping(document["constraints"], "task.constraints")
        _exact_keys(constraints, "task.constraints", {"explicit", "inherited"})
        domains = _mapping(document["domains"], "task.domains")
        _exact_keys(domains, "task.domains", {"canonical", "discovered"})
        risk = _mapping(document["risk"], "task.risk")
        _exact_keys(risk, "task.risk", {"level", "flags"})
        risk_level = Evidence.from_dict(_mapping(risk["level"], "task.risk.level"), "task.risk.level")
        if risk_level.value not in RISK_LEVELS:
            raise TaskValidationError(f"task.risk.level.value is unsupported: {risk_level.value}")
        intent = Evidence.from_dict(document["intent"], "task.intent")
        if intent.value not in INTENTS:
            raise TaskValidationError(f"task.intent.value is unsupported: {intent.value}")
        operation = Evidence.from_dict(document["operation"], "task.operation")
        if operation.value not in OPERATIONS:
            raise TaskValidationError(f"task.operation.value is unsupported: {operation.value}")
        requested_output = Evidence.from_dict(document["requested_output"], "task.requested_output")
        if requested_output.value not in REQUESTED_OUTPUTS:
            raise TaskValidationError(
                f"task.requested_output.value is unsupported: {requested_output.value}"
            )

        confidence_document = _mapping(document["confidence"], "task.confidence")
        required_confidence = {"overall", "project", "intent", "domains"}
        _exact_keys(confidence_document, "task.confidence", required_confidence)
        confidence = {
            key: _require_confidence(confidence_document[key], f"task.confidence.{key}")
            for key in sorted(required_confidence)
        }

        parent_task_id = document.get("parent_task_id")
        continuation_of = document.get("continuation_of")
        for field, value in (("task.parent_task_id", parent_task_id), ("task.continuation_of", continuation_of)):
            if value is not None:
                normalized = _require_string(value, field).strip()
                if not normalized.startswith(TASK_ID_PREFIX):
                    raise TaskValidationError(f"{field} must use tsk_ namespace")
                if field.endswith("parent_task_id"):
                    parent_task_id = normalized
                else:
                    continuation_of = normalized

        return cls(
            task_id=task_id,
            created_at=_require_string(document["created_at"], "task.created_at").strip(),
            lifecycle=lifecycle,
            project=ProjectResolution.from_dict(document["project"]),
            raw_request=raw_request,
            intent=intent,
            operation=operation,
            requested_output=requested_output,
            explicit_constraints=_require_string_tuple(constraints["explicit"], "task.constraints.explicit"),
            inherited_constraints=_require_string_tuple(constraints["inherited"], "task.constraints.inherited"),
            entities=_require_string_tuple(document["entities"], "task.entities"),
            canonical_domains=_require_string_tuple(domains["canonical"], "task.domains.canonical"),
            discovered_domains=_require_string_tuple(domains["discovered"], "task.domains.discovered"),
            risk_level=risk_level,
            risk_flags=_require_string_tuple(risk["flags"], "task.risk.flags"),
            context_needs=_require_string_tuple(document["context_needs"], "task.context_needs"),
            ambiguities=_require_string_tuple(document["ambiguities"], "task.ambiguities"),
            confidence=confidence,
            parent_task_id=parent_task_id,
            continuation_of=continuation_of,
        )

    def to_dict(self) -> dict[str, Any]:
        result = {
            "schema_version": TASK_SCHEMA_VERSION,
            "task_id": self.task_id,
            "created_at": self.created_at,
            "lifecycle": self.lifecycle,
            "project": self.project.to_dict(),
            "request": {"raw": self.raw_request},
            "intent": self.intent.to_dict(),
            "operation": self.operation.to_dict(),
            "requested_output": self.requested_output.to_dict(),
            "constraints": {
                "explicit": list(self.explicit_constraints),
                "inherited": list(self.inherited_constraints),
            },
            "entities": list(self.entities),
            "domains": {
                "canonical": list(self.canonical_domains),
                "discovered": list(self.discovered_domains),
            },
            "risk": {"level": self.risk_level.to_dict(), "flags": list(self.risk_flags)},
            "context_needs": list(self.context_needs),
            "ambiguities": list(self.ambiguities),
            "confidence": dict(self.confidence),
        }
        if self.parent_task_id is not None:
            result["parent_task_id"] = self.parent_task_id
        if self.continuation_of is not None:
            result["continuation_of"] = self.continuation_of
        return result


def validate_task(document: Mapping[str, Any]) -> TaskEnvelope:
    """Validate and normalize an envelope supplied across a process boundary."""
    return TaskEnvelope.from_dict(document)


def render_task_json(envelope: TaskEnvelope) -> str:
    """Render the machine contract with deterministic field ordering."""
    return json.dumps(envelope.to_dict(), ensure_ascii=False, indent=2) + "\n"


def _human_summary(envelope: TaskEnvelope) -> str:
    project = envelope.project.project_id or "unresolved"
    domains = ", ".join(envelope.canonical_domains) or "unknown"
    constraints = ", ".join(envelope.explicit_constraints) or "none"
    return (
        f"Task: {envelope.task_id}\n"
        f"Project: {project} ({envelope.project.status})\n"
        f"Intent: {envelope.intent.value}\n"
        f"Operation: {envelope.operation.value}\n"
        f"Domains: {domains}\n"
        f"Explicit constraints: {constraints}\n"
        f"Risk: {envelope.risk_level.value}\n"
    )


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Analyze one task without writing canonical state.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    analyze = subparsers.add_parser("analyze", help="Build a deterministic TaskEnvelope")
    analyze.add_argument("--vault", default=".", help="Vault containing .claude/project-registry.json")
    analyze.add_argument("--project-root", default=".", help="Project root to resolve read-only")
    analyze.add_argument("--request", required=True, help="Raw user request to preserve in the envelope")
    analyze.add_argument("--json", action="store_true", help="Emit the machine contract")
    arguments = parser.parse_args(argv)
    try:
        envelope = TaskAnalyzer(arguments.vault, arguments.project_root).analyze(arguments.request)
    except (TaskValidationError, TaskProjectResolutionError) as exc:
        if arguments.json:
            print(json.dumps({"error": {"code": "TASK_ANALYSIS_ERROR", "message": str(exc)}}))
        else:
            parser.error(str(exc))
        return 2
    print(render_task_json(envelope) if arguments.json else _human_summary(envelope), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
