"""Stable package namespace for Brain-Eleven's core business logic.

Migration is intentionally incremental.  Legacy ``scripts`` entry points may
remain as compatibility adapters while their implementation moves here.
"""

__all__ = ["memory", "projects", "state"]
