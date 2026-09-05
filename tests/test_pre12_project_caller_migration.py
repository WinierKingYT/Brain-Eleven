from __future__ import annotations

from brain_eleven.projects.registry import ProjectRegistry, ProjectRegistryError
from capture_event import ProjectRegistry as CaptureProjectRegistry
from capture_event import ProjectRegistryError as CaptureProjectRegistryError
from context_router.adapters import ProjectRegistry as AdapterProjectRegistry
from context_router.adapters import ProjectRegistryError as AdapterProjectRegistryError
from state_resolver import ProjectRegistry as ResolverProjectRegistry
from state_resolver import ProjectRegistryError as ResolverProjectRegistryError
from task_model import ProjectRegistry as TaskProjectRegistry
from task_model import ProjectRegistryError as TaskProjectRegistryError


def test_read_only_resolution_callers_use_the_package_boundary() -> None:
    assert CaptureProjectRegistry is ProjectRegistry
    assert AdapterProjectRegistry is ProjectRegistry
    assert ResolverProjectRegistry is ProjectRegistry
    assert TaskProjectRegistry is ProjectRegistry
    assert CaptureProjectRegistryError is ProjectRegistryError
    assert AdapterProjectRegistryError is ProjectRegistryError
    assert ResolverProjectRegistryError is ProjectRegistryError
    assert TaskProjectRegistryError is ProjectRegistryError
