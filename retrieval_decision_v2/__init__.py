"""Phase PRE-08 task-need retrieval decisions.

This package is a read-only selector over the content-free Router and
metadata-first Authority contracts.  It never writes canonical authorities
and it cannot widen the scope trusted by the Router.
"""

from .engine import RetrievalDecisionEngine
from .models import (
    DecisionOptions,
    DecisionResult,
    Need,
    NeedPlan,
    SelectedCandidate,
)

__all__ = [
    "DecisionOptions",
    "DecisionResult",
    "Need",
    "NeedPlan",
    "RetrievalDecisionEngine",
    "SelectedCandidate",
]
