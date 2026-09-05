"""PRE-09 deterministic diversity and context-density decisions.

The package is a read-only post-selection layer.  It consumes the content-free
PRE-08 decision contract and never performs retrieval or canonical writes.
"""

from .engine import ContextDensityEngine
from .models import DensityOptions, DensityResult, DensitySelectedCandidate

__all__ = ["ContextDensityEngine", "DensityOptions", "DensityResult", "DensitySelectedCandidate"]
