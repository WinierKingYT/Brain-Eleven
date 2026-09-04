"""Phase 18 metadata-first, read-only authority resolution."""

from .models import (
    AuthorityOptions,
    ClaimEnvelope,
    ConflictSet,
    ExplanationEntry,
    ResolutionCandidate,
    ResolutionResult,
)
from .resolver import AuthorityResolver

__all__ = [
    "AuthorityOptions",
    "AuthorityResolver",
    "ClaimEnvelope",
    "ConflictSet",
    "ExplanationEntry",
    "ResolutionCandidate",
    "ResolutionResult",
]
