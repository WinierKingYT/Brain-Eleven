"""Stable package surface for trusted transcript path resolution."""

from __future__ import annotations

from brain_eleven._legacy import load_legacy_module


_legacy = load_legacy_module("capture_provenance", "capture_provenance.py")

TranscriptProvenanceError = _legacy.TranscriptProvenanceError
resolve_transcript_path = _legacy.resolve_transcript_path

__all__ = ["TranscriptProvenanceError", "resolve_transcript_path"]
