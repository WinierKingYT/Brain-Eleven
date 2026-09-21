# IG-07 Slice 2B Plan — Entity Extraction and Graph Projection Inversion

**Status:** PLAN ONLY — no production implementation is authorized by this document.
**Repository:** `WinierKingYT/Brain-Eleven`
**Audited HEAD:** `26f35a6`
**Scope:** `entity_extractor.py` and `knowledge_graph.py` only.

Slice 2B is a direction inversion, not a simple file copy. The current
package surfaces import the legacy scripts. The target state is the reverse:
the package owns the implementation and each legacy script is a thin
compatibility/direct-execution adapter. `MemoryStore`, `StateStore`,
`ProjectRegistry`, capture, retrieval, task-state context, and Phase 20 remain
outside this slice.

## 1. Current bridge mechanics

### Entity extraction

The current implementation is still entirely in
`scripts/entity_extractor.py` (306 physical lines, 260 nonblank lines). Its
imports at lines 31–33 are:

- `scripts.logging_config.setup_logging` at line 31;
- `brain_eleven.graph.KnowledgeGraph` and
  `KnowledgeGraphProjectionStale` at line 32;
- `brain_eleven.memory.MemoryStore` and `infer_memory_scope` at line 33.

The implementation objects are defined in the script:

- `TECH_LEXICON` at lines 39–56;
- `PHASE_PATTERN` at line 58;
- `ProjectionInvariantError` at lines 61–63;
- `_slugify` at lines 65–66;
- `EntityExtractor` at lines 69–293, including `build_graph` at lines 247–293;
- direct CLI at lines 296–306.

The package direction currently points backwards. At
`brain_eleven/extraction/__init__.py:11-16`, the package imports
`PHASE_PATTERN`, `TECH_LEXICON`, `EntityExtractor`, and
`ProjectionInvariantError` from `scripts.entity_extractor`. The same names
are re-exported by `__all__` at lines 35–39. There is no
`brain_eleven/extraction/entities.py` at the audited HEAD; the requested target
file must therefore be created during implementation.

The current identity chain is effectively:

```text
brain_eleven.extraction.__init__
        -> scripts.entity_extractor (implementation)
scripts/remember.py:59-61
        -> dynamically loads scripts/entity_extractor.py
```

`scripts/remember.py` uses the legacy loader at lines 46–53 and binds
`EntityExtractor` at line 61, then rebuilds the graph at line 156. This is the
only non-bridge production loader that still reaches the script directly.

### Knowledge graph

The current implementation is entirely in `scripts/knowledge_graph.py` (394
physical lines, 340 nonblank lines). Its relevant imports are:

- standard persistence and typing imports at lines 19–25;
- `networkx` at line 27;
- `scripts.logging_config.setup_logging` at line 29;
- `brain_eleven.memory.MemoryStore`, `MemoryStoreError`, and
  `infer_memory_scope` at line 30.

The implementation objects are:

- `KNOWLEDGE_GRAPH_SCHEMA_VERSION` at line 35;
- `KnowledgeGraphProjectionError` at lines 38–40;
- `KnowledgeGraphProjectionStale` at lines 42–44;
- `_utc_now` at lines 46–47;
- `KnowledgeGraph` at lines 50–381;
- direct demonstration CLI at lines 384–394.

The package projection is currently a re-export bridge. At
`brain_eleven/graph/projection.py:11-16`, it imports
`KNOWLEDGE_GRAPH_SCHEMA_VERSION`, `KnowledgeGraph`,
`KnowledgeGraphProjectionError`, and `KnowledgeGraphProjectionStale` from
`scripts.knowledge_graph`. Its `__all__` at lines 18–23 re-exports those same
objects. `brain_eleven/graph/__init__.py:3-8` then imports them from
`.projection` and exposes them again at lines 10–14.

The current identity chain is therefore:

```text
brain_eleven.graph.__init__
        -> brain_eleven.graph.projection
        -> scripts.knowledge_graph (implementation)
scripts/entity_extractor.py:32
        -> brain_eleven.graph (which returns the script class today)
```

The package bridge docstrings explicitly describe this temporary direction at
`brain_eleven/extraction/__init__.py:3-6` and
`brain_eleven/graph/projection.py:3-6`; those statements must be rewritten when
the inversion is implemented.

## 2. Target inversion strategy

The migration must preserve one implementation object for every public class,
constant, and exception. No second copy may remain active in `scripts/`.

### Step B2.1 — Invert graph projection first

`brain_eleven/graph/projection.py` already has the right package location, so
it becomes the canonical implementation module. Move the complete graph
implementation there, including persistence, projection status, scope
filtering, query methods, and CLI support if direct package execution is
retained. Replace its imports with package-owned dependencies where available,
especially `brain_eleven.support.setup_logging` and the existing
`brain_eleven.memory` surface.

Rewrite `scripts/knowledge_graph.py` as the same `_load_canonical`-style thin
adapter used by Slice 1 and Slice 2A:

1. put the repository root on `sys.path` only for historical direct execution;
2. load `brain_eleven.graph.projection` once and cache it;
3. re-export the schema constant, graph class, and both projection exceptions;
4. preserve the old bare-module alias and direct demonstration CLI;
5. contain no graph class, persistence function, or alternate implementation.

`brain_eleven/graph/__init__.py` remains a public barrel and imports only from
`.projection`. After this step, the unchanged legacy `scripts/entity_extractor.py`
can continue importing `brain_eleven.graph`; it will automatically consume the
new canonical graph implementation during the intermediate state.

### Step B2.2 — Invert entity extraction second

Create `brain_eleven/extraction/entities.py` and move the implementation from
`scripts/entity_extractor.py` into it. The moved module owns:

- `TECH_LEXICON`, `PHASE_PATTERN`, and `_slugify`;
- `ProjectionInvariantError`;
- `EntityExtractor` and all extraction/projection validation methods;
- the direct CLI only if package execution is intentionally supported.

Change its imports to package surfaces (`brain_eleven.support`,
`brain_eleven.graph`, and `brain_eleven.memory`). The graph dependency is then
already canonical because Step B2.1 completed first.

Change `brain_eleven/extraction/__init__.py` to import these names from
`.entities`, retain the semantic extraction exports, and document that the
package owns the implementation.

Rewrite `scripts/entity_extractor.py` as a thin compatibility/direct-execution
adapter. It must expose the exact package objects, retain the historical bare
`entity_extractor` name used by tests and callers, and preserve the old CLI
arguments/output. The adapter may keep explicit package imports needed by the
caller-migration contract, but it must not define a second extractor.

### Object identity contract

After both steps, all of these must be identical objects, not merely behaviorally
equivalent:

```text
brain_eleven.extraction.EntityExtractor
brain_eleven.extraction.entities.EntityExtractor
scripts.entity_extractor.EntityExtractor
bare entity_extractor.EntityExtractor

brain_eleven.graph.KnowledgeGraph
brain_eleven.graph.projection.KnowledgeGraph
scripts.knowledge_graph.KnowledgeGraph
bare knowledge_graph.KnowledgeGraph
```

The same identity rule applies to constants and projection exceptions. The
legacy aliases must not create a second module instance that changes class
identity.

## 3. Dependency order and intermediate state

The graph projection moves first because the entity implementation already
imports `brain_eleven.graph` at `scripts/entity_extractor.py:32`. During the
intermediate state:

1. `brain_eleven.graph.projection` owns `KnowledgeGraph`.
2. `scripts/knowledge_graph.py` is an adapter.
3. `scripts/entity_extractor.py` remains the old implementation but consumes
   the canonical graph through `brain_eleven.graph`.
4. `brain_eleven.extraction.__init__` still temporarily bridges to the old
   entity script until Step B2.2.

This keeps graph callers working while entity extraction is still being tested.
Only after graph identity, persistence, and revision tests pass should the
entity implementation be moved. The final state has no package-to-script
imports in either extraction or graph package.

The implementation should be committed in bounded slices so a failed graph
projection review does not leave an unreviewed entity rewrite mixed into the
same change:

1. graph contract and identity tests;
2. graph canonical implementation and adapter;
3. graph parity/regression evidence;
4. entity canonical implementation and package exports;
5. entity adapter and parity tests;
6. combined Slice 2B report.

No one of these commits authorizes the next slice. Independent review remains
required after the combined evidence is available.

## 4. Revision, lock, corruption, and scope invariants

The inversion must preserve the current derived-projection contract exactly.

### Graph envelope and revision

- The persisted envelope remains schema version `2` and projection name
  `knowledge_graph` (`scripts/knowledge_graph.py:73-83`, `158-163`).
- `source_memory_revision` remains a non-negative integer and is compared with
  `MemoryStore.revision()` (`:80-93`, `:107-122`).
- A loaded graph reports `fresh`, `stale`, `missing`, `legacy`, `corrupt`, or
  `source_unavailable` with the same meanings and error visibility.
- Legacy plain node-link files remain readable but explicitly lack a trusted
  source revision; they must not be silently treated as fresh.
- `mark_projection` continues to reject invalid revisions and marks only a
  proven source revision (`:139-147`).

### Rebuild atomicity and stale protection

- `EntityExtractor.build_graph` snapshots the canonical store, clears the
  derived graph, extracts only active and approved memories, and records the
  starting revision (`scripts/entity_extractor.py:247-264`).
- Before publishing, it re-reads the canonical revision and raises
  `KnowledgeGraphProjectionStale` if the store changed (`:277-285`).
- Projection consistency still verifies eligible memory nodes, project
  `BELONGS_TO` edges, and a fresh projection (`:100-164`).
- Graph persistence remains temp-file + flush + fsync + replace, with the
  previous graph copied to its backup first (`scripts/knowledge_graph.py:149-187`).
- The migration adds no MemoryStore write path, no new authority, and no
  bypass around existing MemoryStore locking/CAS or corruption handling.

### Corruption, locking, and scope

- JSON, OS, schema, node-link, and type failures continue to become visible
  projection corruption with an empty in-memory graph (`:67-105`).
- `MemoryStoreError` remains mapped to `source_unavailable` during status
  checks (`:107-119`); exception type and message parity must be tested.
- Graph query, traversal, relationship, and entity visibility rules remain
  unchanged, including global/project/default/all scopes
  (`scripts/knowledge_graph.py:242-355`).
- A project graph may not expose another project's memory or project node.
  Existing project-scope tests are hard regression gates.
- Entity extraction continues to represent technology and phase matches as
  mentions/relations. Moving code must not promote lexical matches into
  stronger semantic relationships.

## 5. Current caller inventory

The inventory distinguishes a direct legacy implementation dependency from a
caller that already consumes the package surface. This avoids hiding the real
blast radius behind the old `2 production / 5 test` summary.

### Entity extractor

**Direct legacy bridge/loader (2 production files, the old inventory count):**

| File | Reference | Role |
|---|---|---|
| `brain_eleven/extraction/__init__.py` | `:11-16` | package-to-script bridge; must be inverted |
| `scripts/remember.py` | `:46-61`, `:156` | dynamic legacy loader and graph rebuild caller; must be switched to the package surface |

**Existing package-surface production callers that must remain compatible (4):**

| File | Reference | Role |
|---|---|---|
| `brain_eleven/runtime/maintenance.py` | `:34`, `:58` | canonical maintenance runtime imports `brain_eleven.extraction` |
| `scripts/memory_backup.py` | `:26`, `:473` | restore/disaster drill rebuilds the derived graph |
| `scripts/post_session_maintenance.py` | `:25` | legacy adapter exposes the package extractor to maintenance |
| `scripts/search-api.py` | `:76`, `:152-166` | API graph rebuild path imports the package extractor |

**Direct bare legacy test callers (6, one more than the old 5-file count):**

- `tests/test_graph_projection_revision.py:10`;
- `tests/test_memory_backup.py:13`;
- `tests/test_phase11_graph_chat.py:18`;
- `tests/test_phase14_graduation_failures.py:17`;
- `tests/test_phase14_scope.py:13`;
- `tests/test_pre12_memory_state_caller_migration.py:387` (identity check).

The following integration tests exercise entity extraction indirectly and must
also remain green: `tests/test_search_api.py`,
`tests/test_post_session_maintenance.py`, `tests/test_remember.py`, and the
graph/scope tests listed above. `conftest.py:48` is test infrastructure that
aliases the historical module name; it is not a production caller.

### Knowledge graph

**Direct legacy bridge/implementation dependency (2 production files, the old
inventory count):**

| File | Reference | Role |
|---|---|---|
| `brain_eleven/graph/projection.py` | `:11-16` | package-to-script bridge; becomes the implementation |
| `scripts/entity_extractor.py` | `:32`, `:101`, `:180`, `:247` | entity implementation consumes the graph surface; remains compatible during Step B2.1 |

**Existing package-surface production callers (5 external callers):**

- `context_router/adapters.py:10`, `:281`;
- `brain_eleven/runtime/chat_interface.py:39`, `:123`;
- `scripts/chat_interface.py:34` (compatibility export);
- `scripts/search-api.py:75`, `:152-198`;
- `brain_eleven/graph/__init__.py:3-8` (public package barrel).

`scripts/entity_extractor.py` is listed in both groups because it currently
imports the package surface while that surface resolves back to the script;
the inversion must remove this cycle.

**Direct bare legacy test callers (5, unchanged from the old count):**

- `tests/test_graph_projection_revision.py:11`;
- `tests/test_phase11_graph_chat.py:17`;
- `tests/test_phase14_graduation_failures.py:18`;
- `tests/test_phase14_scope.py:14`;
- `tests/test_remember.py:12`.

Additional package/integration coverage that must remain green includes
`tests/test_search_api.py`, `tests/test_context_router.py`,
`tests/test_post_session_maintenance.py`, `tests/test_memory_backup.py`, and
`tests/test_pre12_memory_state_caller_migration.py:373-375`. `conftest.py:52`
is only the test alias for the historical bare module.

## 6. Five-gate regression evidence plan

The same gates used by Slice 1 and Slice 2A apply to both modules.

### Gate 1 — identity proof

Add focused tests importing package modules, `scripts.*` adapters, and the
historical bare names. Assert `is` identity for classes, constants, and
exceptions. Assert that the entity extractor constructed in a package caller
returns a canonical graph object.

### Gate 2 — adapter-only AST proof

Parse both legacy scripts with `ast` and assert that they contain no class
definition and no duplicate implementation functions. The only helper may be
the canonical loader. Assert the canonical module path, export list, direct
execution behavior, and absence of old implementation imports from package
code after inversion.

### Gate 3 — parity and failure proof

Run the existing behavioral tests unchanged, then add package/legacy parity
cases for:

- graph envelope round-trip and backup behavior;
- missing, legacy, malformed, and corrupt graph documents;
- source revision fresh/stale transitions;
- `MemoryStoreError`/lock failure visibility;
- stale rebuild rejection when the canonical revision changes;
- eligible/ineligible memory filtering and project isolation;
- technology/phase extraction and relationship deduplication;
- direct CLI output and exit behavior.

The same fixture and the same revision-bound expected values must be used for
package and adapter paths. No test may accept a second implementation merely
because its output looks similar.

### Gate 4 — full repository and static checks

Run, on the exact implementation HEAD:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_phase11_graph_chat.py tests/test_graph_projection_revision.py tests/test_phase14_scope.py tests/test_phase14_graduation_failures.py tests/test_memory_backup.py tests/test_remember.py tests/test_search_api.py tests/test_context_router.py tests/test_pre12_memory_state_caller_migration.py -q
.\.venv\Scripts\python.exe -m pytest tests -q
.\.venv\Scripts\flake8.exe brain_eleven/extraction/entities.py brain_eleven/extraction/__init__.py brain_eleven/graph/projection.py brain_eleven/graph/__init__.py scripts/entity_extractor.py scripts/knowledge_graph.py --select E9,F63,F7,F82
.\.venv\Scripts\python.exe -m compileall -q brain_eleven/extraction brain_eleven/graph scripts/entity_extractor.py scripts/knowledge_graph.py
git diff --check
```

Record the exact `git rev-parse HEAD`, test counts, warnings, and any
pre-existing quality failures. A green static suite does not prove graph or
extraction intelligence quality.

### Gate 5 — independent review

A separate read-only reviewer must inspect both diffs, bridge direction,
identity tests, revision/corruption evidence, scope tests, and full-suite
results. The implementation agent must not mark Slice 2B `SHIP`. Only the
independent reviewer may issue `SHIP`, `FIX-FIRST`, or `RETHINK`.

## 7. Estimated change size

These are planning estimates, not implementation commitments:

| Area | Estimated changed lines | Main risk |
|---|---:|---|
| Graph canonical implementation, adapter, exports, focused tests | 450–520 | revision envelope, corruption, and scope behavior |
| Entity canonical implementation, adapter, exports, focused tests | 360–430 | graph dependency order and stale rebuild protection |
| Combined Slice 2B documentation/evidence | 80–120 | evidence must bind to exact revision |
| **Total touched lines** | **890–1,070** | no unrelated cleanup |

The estimate includes moved implementation and test additions, not generated
vault artifacts. It assumes no changes to canonical stores, lifecycle rules,
capture/retrieval, task state, or Phase 20.

## 8. Acceptance boundary and exclusions

Slice 2B is ready for independent review only when:

- both package modules own the implementation;
- both legacy scripts are adapters with preserved direct execution;
- package, script, and bare imports preserve object identity;
- revision, lock, corruption, backup, and scope semantics have parity evidence;
- all listed direct and indirect callers pass unchanged;
- full regression and critical static checks are recorded against an exact SHA;
- no unrelated production file or feature was included.

This plan does not authorize implementation, Phase 20 work, V2 promotion,
semantic extraction tuning, retrieval changes, canonical authority changes, or
`task_state_context.py` migration. A separate bounded contract and independent
review approval are required before any `.py` file is changed.
