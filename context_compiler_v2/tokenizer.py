"""Honest token measurement adapters for Phase 19.

No target-model tokenizer is bundled with the project, so the default adapter is
explicitly conservative.  It deliberately over-estimates short Unicode-heavy
text rather than presenting an estimate as an exact model token count.
"""

from __future__ import annotations

from typing import Protocol

from brain_eleven.runtime.token_estimate import ConservativeTokenEstimator, TokenEstimate

__all__ = ["ConservativeTokenEstimator", "TokenEstimate", "TokenEstimator"]


class TokenEstimator(Protocol):
    def estimate(self, text: str) -> TokenEstimate:
        """Return the cost of exactly this rendered text."""
