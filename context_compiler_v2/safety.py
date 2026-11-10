"""Bridge: the implementation moved to brain_eleven.runtime.secret_check."""

from brain_eleven.runtime.secret_check import contains_secret, escape_untrusted_text

__all__ = ["contains_secret", "escape_untrusted_text"]
