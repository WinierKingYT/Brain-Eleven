# PRE-12 — Repository Consolidation

Status: IMPLEMENTED / PARITY VERIFIED (packages 1–3)

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

## Second migration boundary — canonical stores

The canonical stores are now available from stable package namespaces:

```python
from brain_eleven.memory import MemoryStore
from brain_eleven.state import StateStore
```

`brain_eleven.memory.store` and `brain_eleven.state.store` re-export the
existing implementations from `scripts/memory_store.py` and
`scripts/state_store.py`. This identity-preserving adapter keeps schema
versions, revisions, locking, corruption handling, typed state transitions,
and error classes owned by the existing authorities. Package parity tests
cover object identity and temporary-vault load/persistence behavior.

These package surfaces are the supported destination for future caller
migrations. Legacy imports remain available during the compatibility window.

## Package 3 — read-only caller migration

The first production callers that resolve project identity now import through
`brain_eleven.projects.registry`: capture-event parsing, task analysis, state
resolution, and the context-router adapters. Their legacy module names remain
available for existing scripts and tests, but the caller-level parity tests
verify that both classes and error types are the same canonical objects.

This package intentionally excludes mutating registry operations and does not
change project registration, archive handling, path normalization, or CLI
behavior. Additional callers will move in separate bounded packages.

## Compatibility rules

- no parallel registry implementation may be added;
- package and legacy imports must expose the same implementation objects;
- registry corruption remains an error, never an empty success;
- project IDs, roots, statuses, and proactive-capture semantics are unchanged;
- migration changes require parity tests and a separate verification commit;
- the legacy module is not removed until all callers are migrated and CI has
  verified the compatibility surface.

## Next bounded migrations

1. migrate the remaining read-only project-resolution callers;
2. migrate one bounded set of memory/state callers to the new surfaces;
3. move one implementation at a time with import parity tests;
4. reduce dynamic `sys.path` injection in adapters;
5. keep scripts as thin CLI/hook adapters only.

PRE-12 is not complete merely because the namespace exists.  Completion
requires one maintained implementation per responsibility, preserved CLI
behavior, and a clean removal review for each legacy wrapper.
