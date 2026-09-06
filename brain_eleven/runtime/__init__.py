"""PRE-13 local runtime. Importing the package never starts a service."""

RUNTIME_VERSION = 1

# The Foundation implementations still live behind the shared legacy bridge.
from brain_eleven import _legacy  # noqa: F401,E402
