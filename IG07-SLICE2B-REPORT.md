# IG-07 Slice 2B — Combined Package Report

## PACKAGE

IG-07 Slice 2B — graph projection (B2.1) and entity extraction inversion
(B2.2)

## REVISION

Validation HEAD: `38b9728`  
B2.1 implementation: `63aa77d`  
B2.1 tests: `080b089`  
B2.1 independent review / SHIP: `9dc6344`  
B2.2 identity tests: `351de87`  
B2.2 canonical implementation and adapter: `143cb26`  
B2.2 parity/regression tests: `da8caed`  
B2.2 caller update: `38b9728`

## OBJECTIVE

Invert both bridge directions so that package modules own graph projection and
deterministic entity extraction, while legacy scripts remain thin,
direct-execution-compatible adapters. Preserve object identity, revision-bound
projection safety, eligible-memory filtering, relationship semantics, scope
isolation, and canonical authority boundaries.

## FILES CHANGED

### B2.1 — graph projection

- `brain_eleven/graph/projection.py` became the canonical graph implementation.
- `scripts/knowledge_graph.py` became a cached canonical adapter.
- `brain_eleven/extraction/__init__.py` received the interim graph-ownership
  documentation update.
- `tests/test_graph_projection_package_migration.py` added migration/parity
  evidence.

B2.1 was independently reviewed and accepted as `SHIP` at `9dc6344`.

### B2.2 — entity extraction

- `brain_eleven/extraction/entities.py` now owns `TECH_LEXICON`,
  `PHASE_PATTERN`, `_slugify`, `ProjectionInvariantError`, `EntityExtractor`,
  projection validation, rebuild logic, and the historical CLI.
- `brain_eleven/extraction/__init__.py` now exports entity objects from
  `.entities` while retaining all semantic extraction exports.
- `scripts/entity_extractor.py` is a thin cached adapter with the historical
  bare-module alias and CLI delegation.
- `scripts/remember.py` now imports `EntityExtractor` from
  `brain_eleven.extraction`; it no longer dynamically loads the legacy entity
  script.
- `tests/test_entity_extraction_identity.py` and
  `tests/test_entity_extraction_package_migration.py` add identity, adapter
  AST, parity, stale rebuild, eligibility, scope, relationship, and CLI tests.

Unchanged by B2.2: `brain_eleven/graph/*`, `scripts/knowledge_graph.py`,
`MemoryStore`, `StateStore`, `ProjectRegistry`, capture/retrieval paths,
`task_state_context.py`, and Phase 20.

## ROOT CAUSES ADDRESSED

- Package extraction and graph surfaces no longer re-export script-owned
  implementations.
- Legacy import and direct-execution paths resolve to one canonical object set.
- The `remember.py` capture path no longer creates a second entity-loader path.
- Graph projection and entity rebuild remain derived, revision-bound operations;
  no new canonical write authority was introduced.

## TESTS ADDED

- B2.1: 10 graph migration/parity tests.
- B2.2: 1 identity test and 7 migration/parity tests (8 total; malformed/state
  cases are covered by the existing graph suite and the new focused cases).

Existing behavioral tests were not modified.

## TESTS EXECUTED

- B2.2 focused graph/entity/scope/backup/remember/runtime/migration suite:
  **203 passed, 2 warnings**.
- Full repository suite (`pytest tests -q`): **913 passed, 2 warnings** in
  157.85 seconds.
- Critical flake8 (`E9,F63,F7,F82`) over the planned package/adapter surface:
  **PASS**.
- `compileall` over extraction, graph, and both legacy adapters: **PASS**.
- Four-surface identity check for entity classes, constants, and exception:
  **PASS**.
- Adapter-only AST check: **PASS**; `scripts/entity_extractor.py` contains no
  class or duplicate implementation function.
- `git diff --check`: **PASS**.

## QUALITY METRICS BEFORE / AFTER

This is an architecture/ownership migration, not an intelligence-quality
tuning package. Behavioral quality is therefore reported as parity: all
focused and full regression gates remained green while implementation authority
moved into `brain_eleven/`.

## SAFETY METRICS

- Active + approved memory filtering: PASS.
- Stale canonical revision rejection before graph publication: PASS.
- Technology/phase lexical relationships and deduplication: PASS.
- Project/global visibility isolation: PASS.
- Canonical graph and entity object identity across package, adapter, and bare
  module surfaces: PASS.
- No new MemoryStore write path, authority, or lock/CAS bypass: PASS by diff
  and focused regression.

## KNOWN LIMITATIONS

- B2.2 independent read-only review has not yet been performed.
- Remote CI was not rerun in this implementation turn; local exact-HEAD
  evidence is recorded above.
- Slice 2B cannot be declared closed until the combined independent review
  issues its verdict.

## OPEN FAILURES

No local test, parity, static, compile, identity, or CLI failures remain.
Independent review/acceptance is the only open gate for this package.

## INDEPENDENT REVIEW

- B2.1: **SHIP**, independently recorded in
  `IG07-SLICE2B-B21-INDEPENDENT-REVIEW.md`.
- B2.2 and the combined Slice 2B package: **PENDING**.

## SCORE BEFORE / AFTER

No intelligence score is raised by this migration. Architecture ownership and
compatibility evidence improved; extraction, retrieval, correction, and
daily-use quality scores remain otherwise unchanged pending later evaluation.

## VERDICT

**REVIEW PENDING / NO SELF-SHIP**

