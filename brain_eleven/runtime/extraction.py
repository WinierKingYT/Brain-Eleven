"""Stable package surface for deterministic capture extraction."""

from __future__ import annotations

from brain_eleven._legacy import load_legacy_module


_legacy = load_legacy_module("extraction", "extraction.py")

EXTRACTION_SCHEMA_VERSION = _legacy.EXTRACTION_SCHEMA_VERSION
EXTRACTOR_VERSION = _legacy.EXTRACTOR_VERSION
Commitment = _legacy.Commitment
CandidateKind = _legacy.CandidateKind
MemoryType = _legacy.MemoryType
StateOperation = _legacy.StateOperation
ExtractedBase = _legacy.ExtractedBase
NewMemoryCandidate = _legacy.NewMemoryCandidate
StateMutationProposal = _legacy.StateMutationProposal
QuarantineCandidate = _legacy.QuarantineCandidate
ExtractionEnvelope = _legacy.ExtractionEnvelope
DeterministicExtractor = _legacy.DeterministicExtractor
extract = _legacy.extract

# These helpers are intentionally exposed because the worker's bounded
# fallback path uses the same classification rules as the extractor.
_segments = _legacy._segments
_classify_commitment = _legacy._classify_commitment
_memory_type = _legacy._memory_type

__all__ = [
    "EXTRACTION_SCHEMA_VERSION",
    "EXTRACTOR_VERSION",
    "Commitment",
    "CandidateKind",
    "MemoryType",
    "StateOperation",
    "ExtractedBase",
    "NewMemoryCandidate",
    "StateMutationProposal",
    "QuarantineCandidate",
    "ExtractionEnvelope",
    "DeterministicExtractor",
    "extract",
]
