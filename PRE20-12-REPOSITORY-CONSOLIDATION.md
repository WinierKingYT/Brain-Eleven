# PRE-12 — Repository Consolidation

Status: IMPLEMENTED / PARITY VERIFIED (packages 1–10)

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

The capture hook also retains a narrow standalone fallback to the legacy
module. This is required for deployed/copied hook environments that contain
the hook adapter and its local support files but do not install the repository
package tree; normal repository imports still use the canonical package.

This package intentionally excludes mutating registry operations and does not
change project registration, archive handling, path normalization, or CLI
behavior. Additional callers will move in separate bounded packages.

Package 3 verification completed on commit `375aa4c`: Validation #86 passed
on Ubuntu and Windows, including the standalone hook tests, and the dependent
[Docker #86](https://github.com/WinierKingYT/Brain-Eleven/actions/runs/33995608696)
run passed as well. The corresponding
[Validation #86](https://github.com/WinierKingYT/Brain-Eleven/actions/runs/33995287852)
run is the revision-bound CI evidence for this package.

## Package 4 — remaining project-resolution callers

The remaining production and evaluation callers now resolve project identity
through `brain_eleven.projects.registry`: the context compiler, search and
remember adapters, backup and state-boundary utilities, the project-registry
CLI wrapper, and the router, authority, compiler, and task-state evaluation
adapters. This completes the current read-only caller migration without
changing registry semantics or persistence ownership.

Legacy `project_registry` imports are now limited to intentional compatibility
edges: the package backing adapter, the canonical state-store implementation,
and standalone hook/scope fallbacks used when a copied hook environment does
not contain the repository package tree. An AST parity test guards this list
and prevents new production callers from bypassing the package boundary.

The migration also refreshed only the mutable compatibility snapshot
`baseline-v2` because its source fingerprint includes `memory_scope.py`.
Historical `baseline-v1` remains immutable and unchanged. The generated
baseline still reports 130 public cases with the same deterministic metrics.

Package 4 verification completed on commit `b9fb67b`: Validation #89 passed
on Ubuntu and Windows, including coverage, security, Phase 15–19 evidence,
and Context Engine Foundation graduation. The dependent
[Docker #89](https://github.com/WinierKingYT/Brain-Eleven/actions/runs/33996741038)
run passed as well. The corresponding
[Validation #89](https://github.com/WinierKingYT/Brain-Eleven/actions/runs/33996442080)
run is the revision-bound CI evidence for this package.

## Package 5 — canonical memory/state caller migration

The next bounded caller set now uses the canonical memory and state package
surfaces without changing behavior or persistence ownership. Read-only router
and authority adapters, together with the Phase 15–19 evaluation and benchmark
providers, import `MemoryStore` from `brain_eleven.memory` and
`StateService` from `brain_eleven.state` where required. The legacy modules
remain the backing implementations and compatibility edges; no schema, path,
revision, locking, or CLI semantics changed.

Package 5 adds two safeguards: an AST boundary test prevents these migrated
callers from reintroducing direct legacy store imports, and identity checks
prove that package and caller references resolve to the same canonical store
and state-service objects. This keeps the migration strangler-style and avoids
creating a second persistence authority.

Package 5 verification completed on commit `f095015`: Validation #91 passed
on Ubuntu and Windows, including coverage, security, Phase 15–19 evidence,
and Context Engine Foundation graduation. The dependent
[Docker #91](https://github.com/WinierKingYT/Brain-Eleven/actions/runs/33997674238)
run passed as well. The corresponding
[Validation #91](https://github.com/WinierKingYT/Brain-Eleven/actions/runs/33997369425)
run is the revision-bound CI evidence for this package.

## Package 6 — state mutation and CLI caller migration

The typed state CLI, state-boundary proposal adapter, and read-only state
resolver now import canonical stores through `brain_eleven.state` and
`brain_eleven.memory`. This completes the next bounded caller migration while
preserving the existing standalone CLI bootstrap, schemas, filesystem paths,
revision/locking behavior, and persistence ownership. The legacy store modules
remain compatibility/backing edges; they were not duplicated or rewritten.

Package 6 adds an AST boundary check for the migrated state callers and
identity checks proving that resolver references are the same canonical
`MemoryStore` and `StateStore` objects exposed by the package namespaces.

Package 6 verification completed on commit `47ab1d3`: Validation #93 passed
on Ubuntu and Windows, including coverage, security, Phase 15–19 evidence,
and Context Engine Foundation graduation. The dependent
[Docker #93](https://github.com/WinierKingYT/Brain-Eleven/actions/runs/33998686433)
run passed as well. The corresponding
[Validation #93](https://github.com/WinierKingYT/Brain-Eleven/actions/runs/33998344239)
run is the revision-bound CI evidence for this package.

## Package 7 — memory mutation and lifecycle caller migration

The bounded canonical-memory mutation callers now import `MemoryStore`, its
conflict/corruption errors, and the no-op transaction helper through
`brain_eleven.memory`: the lifecycle, truth-engine, and provenance adapters
were migrated without changing mutation semantics. Their `memory_scope` and
`memory_store_lock` imports remain intentional compatibility/backing edges;
they are not additional persistence authorities and were not broadened by this
package.

Package 7 keeps the store schema, revisioning, locking, atomic-write behavior,
CLI behavior, and lifecycle rules unchanged. The migration test adds an AST
boundary for the three callers and identity checks confirm that their imported
store class is the same canonical object exposed by the package surface.

Package 7 verification completed on commit `8826117`: Validation #95 passed
on Ubuntu and Windows, including coverage, security, Phase 15–19 evidence,
and Context Engine Foundation graduation. The corresponding
[Validation #95](https://github.com/WinierKingYT/Brain-Eleven/actions/runs/33999284762)
and [Docker #95](https://github.com/WinierKingYT/Brain-Eleven/actions/runs/33999585254)
runs are the implementation evidence. The documentation follow-up is commit
`8b17e40`; [Validation #96](https://github.com/WinierKingYT/Brain-Eleven/actions/runs/33999656746)
and [Docker #96](https://github.com/WinierKingYT/Brain-Eleven/actions/runs/33999938961)
verify that status record on Ubuntu and Windows as well.

## Package 8 — derived graph caller migration

The derived knowledge-graph projection now has a stable package boundary at
`brain_eleven.graph`. `context_router/adapters.py`,
`scripts/entity_extractor.py`, `scripts/chat_interface.py`, and
`scripts/search-api.py` import the graph surface through that package. The
existing `scripts/knowledge_graph.py` module remains the backing
implementation; graph schema, revision checks, persistence behavior, and
projection semantics are unchanged.

The entity extractor also consumes `MemoryStore` through
`brain_eleven.memory`, keeping the canonical memory boundary consistent while
leaving its compatibility imports otherwise unchanged. AST boundary checks
prevent these callers from reintroducing direct graph imports, and an object
identity test proves that the package surface and caller references resolve to
the same `KnowledgeGraph` implementation.

Package 8 implementation verification completed on commit `a63dcdc`:
[Validation #98](https://github.com/WinierKingYT/Brain-Eleven/actions/runs/34000366880)
and the dependent [Docker #98](https://github.com/WinierKingYT/Brain-Eleven/actions/runs/34000640863)
passed on Ubuntu and Windows, including coverage, security, Phase 15–19
evidence, and Foundation graduation. The documentation follow-up will carry
its own revision-bound CI evidence.

## Package 9 — entity extraction caller migration

Deterministic entity extraction now has a stable package boundary at
`brain_eleven.extraction`. The backup, post-session maintenance, and search
API callers import `EntityExtractor` through that surface. The existing
`scripts/entity_extractor.py` module remains the backing implementation, so
graph rebuild behavior, projection validation, and legacy CLI compatibility
are unchanged.

The package re-exports the extractor's public lexicon, phase pattern, and
projection error alongside the extractor itself. A caller-boundary test rejects
direct production imports and an object-identity test proves that the package
surface and legacy implementation refer to the same class. The maintenance
entrypoint now also bootstraps the repository root before importing the package,
which keeps direct hook execution portable.

Package 9 implementation verification completed on commit `3044b39`:
[Validation #100](https://github.com/WinierKingYT/Brain-Eleven/actions/runs/34001181377)
and [Docker #100](https://github.com/WinierKingYT/Brain-Eleven/actions/runs/34001475029)
passed on Ubuntu and Windows, including coverage, security, Phase 15–19
evidence, and Foundation graduation.

## Package 10 — search surface and caller migration

Search now has a stable package boundary at `brain_eleven.search`. The
package re-exports the existing `MemoryRetriever`, `HybridSearchEngine`,
`SearchResult`, and `MLRanker` implementations through one compatibility-safe
surface. A shared legacy-module loader keeps direct execution portable while
ensuring package imports and the legacy modules resolve to the same objects.

The chat interface and search API now consume the package surface instead of
loading the search implementations independently. The historical hyphenated
scripts remain adapters/backing modules for compatibility; search behavior,
ranking, result shape, and CLI/API behavior are unchanged. The direct hybrid
search entrypoint also bootstraps the repository root before importing the
package, so it remains usable from outside the repository working directory.

Package 10 adds an AST caller-boundary test and an object-identity test. The
tests reject new direct search implementation imports in migrated callers and
prove that package and legacy references are identical. The shared loader
also removes repeated dynamic-loading logic from the migrated search callers
without changing the remaining legacy adapters.

Package 10 implementation verification completed on commit `5d4dec5`:
[Validation #103](https://github.com/WinierKingYT/Brain-Eleven/actions/runs/34002168314)
and [Docker #103](https://github.com/WinierKingYT/Brain-Eleven/actions/runs/34002459052)
passed on Ubuntu and Windows, including coverage, security, Phase 15–19
evidence, and Foundation graduation.

## Compatibility rules

- no parallel registry implementation may be added;
- package and legacy imports must expose the same implementation objects;
- registry corruption remains an error, never an empty success;
- project IDs, roots, statuses, and proactive-capture semantics are unchanged;
- migration changes require parity tests and a separate verification commit;
- the legacy module is not removed until all callers are migrated and CI has
  verified the compatibility surface.

## Next bounded migrations

1. migrate the next bounded API and support callers to the new surfaces;
2. move one implementation at a time with import parity tests;
3. reduce dynamic `sys.path` injection in adapters;
4. keep scripts as thin CLI/hook adapters only.

PRE-12 is not complete merely because the namespace exists.  Completion
requires one maintained implementation per responsibility, preserved CLI
behavior, and a clean removal review for each legacy wrapper.
