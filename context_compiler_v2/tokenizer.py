"""Honest token measurement adapters for Phase 19.

No target-model tokenizer is bundled with the project, so the default adapter is
explicitly conservative.  It deliberately over-estimates short Unicode-heavy
text rather than presenting an estimate as an exact model token count.
"""

from __future__ import annotations

import math
from typing import Protocol

from .models import TokenEstimate


class TokenEstimator(Protocol):
    def estimate(self, text: str) -> TokenEstimate:
        """Return the cost of exactly this rendered text."""


class ConservativeTokenEstimator:
    """UTF-8-byte conservative fallback, independent of provider/network access."""

    adapter = "utf8-conservative-v1"
    version = "1"

    def estimate(self, text: str) -> TokenEstimate:
        if not isinstance(text, str):
            raise TypeError("Token estimation requires text")
        byte_count = len(text.encode("utf-8"))
        # A byte/3 estimate with one token of framing is intentionally more
        # conservative than common English token ratios and safe for Unicode.
        count = 0 if not text else math.ceil(byte_count / 3) + 1
        return TokenEstimate(
            count=count,
            mode="CONSERVATIVE_ESTIMATE",
            adapter=self.adapter,
            version=self.version,
            byte_count=byte_count,
        )
