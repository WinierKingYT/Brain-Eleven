from __future__ import annotations

import ast
from pathlib import Path

from brain_eleven.projects.registry import ProjectRegistry, ProjectRegistryError
from brain_eleven.runtime.capture_event import ProjectRegistry as CaptureProjectRegistry
from brain_eleven.runtime.capture_event import ProjectRegistryError as CaptureProjectRegistryError
from brain_eleven.state.resolver import ProjectRegistry as ResolverProjectRegistry
from brain_eleven.state.resolver import ProjectRegistryError as ResolverProjectRegistryError
from brain_eleven.runtime.task import ProjectRegistry as TaskProjectRegistry
from brain_eleven.runtime.task import ProjectRegistryError as TaskProjectRegistryError


def test_read_only_resolution_callers_use_the_package_boundary() -> None:
    assert CaptureProjectRegistry is ProjectRegistry
    assert ResolverProjectRegistry is ProjectRegistry
    assert TaskProjectRegistry is ProjectRegistry
    assert CaptureProjectRegistryError is ProjectRegistryError
    assert ResolverProjectRegistryError is ProjectRegistryError
    assert TaskProjectRegistryError is ProjectRegistryError



