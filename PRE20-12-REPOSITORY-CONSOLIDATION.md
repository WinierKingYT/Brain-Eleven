# PRE-12 — Repository Consolidation

Status: IMPLEMENTED / PARITY VERIFIED

## Purpose

PRE-12 moves Brain-Eleven business logic behind stable Python package
namespaces without rewriting the frozen Memory Foundation or changing CLI
behavior.  Migration follows a strangler path:

1. define the package boundary;
2. expose the existing implementation through that boundary;
3. add parity tests;
4. migrate callers in bounded domains;
5. leave thin compatibility adapters in `scripts/`;
6. remove duplicate implementations only after the compatibility window.

## Protected authorities

- `MemoryStore` remains the canonical memory authority.
- `StateStore` remains the canonical current-state authority.
- `ProjectRegistry` remains the canonical project identity/lifecycle authority.
- Router, Authority Resolver, and Compiler V2 contracts remain unchanged.

This package does not change schemas, revisions, locking, filesystem paths,
or persistence behavior.

## First migration boundary

The project registry is now available from:

```python
from brain_eleven.projects.registry import ProjectRegistry
```

The legacy `scripts/project_registry.py` implementation remains the backing
module for this first boundary.  This is deliberate: importing the package
must preserve object identity and avoid the historical eager imports in
`scripts/__init__.py`.  New code may depend on the package namespace; old
callers remain supported during the parity window.

## Compatibility rules

- no parallel registry implementation may be added;
- package and legacy imports must expose the same implementation objects;
- registry corruption remains an error, never an empty success;
- project IDs, roots, statuses, and proactive-capture semantics are unchanged;
- migration changes require parity tests and a separate verification commit;
- the legacy module is not removed until all callers are migrated and CI has
  verified the compatibility surface.

## Next bounded migrations

1. migrate read-only project-resolution callers;
2. establish `brain_eleven.memory` and `brain_eleven.state` package surfaces;
3. move one implementation at a time with import parity tests;
4. reduce dynamic `sys.path` injection in adapters;
5. keep scripts as thin CLI/hook adapters only.

PRE-12 is not complete merely because the namespace exists.  Completion
requires one maintained implementation per responsibility, preserved CLI
behavior, and a clean removal review for each legacy wrapper.
