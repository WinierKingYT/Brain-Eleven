"""Honest token measurement adapters.

No target-model tokenizer is bundled with the project, so the default adapter is
explicitly conservative.  It deliberately over-estimates short Unicode-heavy
text rather than presenting an estimate as an exact model token count.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

ESTIMATION_MODES = frozenset({"EXACT", "PROVIDER_ESTIMATE", "CONSERVATIVE_ESTIMATE"})


def _string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value.strip()


@dataclass(frozen=True)
class TokenEstimate:
    count: int
    mode: str
    adapter: str
    version: str
    byte_count: int

    def __post_init__(self) -> None:
        if isinstance(self.count, bool) or not isinstance(self.count, int) or self.count < 0:
            raise ValueError("token estimate count must be a non-negative integer")
        if self.mode not in ESTIMATION_MODES:
            raise ValueError(f"Unsupported token estimate mode: {self.mode}")
        _string(self.adapter, "token estimator adapter")
        _string(self.version, "token estimator version")
        if isinstance(self.byte_count, bool) or not isinstance(self.byte_count, int) or self.byte_count < 0:
            raise ValueError("token estimate byte_count must be a non-negative integer")

    def to_dict(self) -> dict[str, Any]:
        return {
            "count": self.count,
            "mode": self.mode,
            "adapter": self.adapter,
            "version": self.version,
            "byte_count": self.byte_count,
        }


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
