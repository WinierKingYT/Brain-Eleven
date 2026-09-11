# IG-07 Slice 2D — D1 Package Report

**PACKAGE:** IG-07 / Slice 2D / D1 (`remember.py`)
**IMPLEMENTATION REVISION:** `3c1f557` (including `d1d563d` and `9d089a2`)
**OBJECTIVE:** Move manual memory capture orchestration into the canonical
`brain_eleven.memory.capture` package while preserving the existing validator
transaction authority and legacy CLI/import compatibility.

## FILES CHANGED

- `brain_eleven/memory/capture.py` — canonical `remember`, default/project
  helpers, proactive policy surface, CLI, and legacy safety/validator bridges.
- `brain_eleven/memory/__init__.py` — lazy capture exports to keep the package
  import graph acyclic while exposing the package surface.
- `scripts/remember.py` — cached thin compatibility/direct-execution adapter;
  no capture implementation or direct persistence remains.
- `scripts/remember_opt_in.py` — proactive policy caller switched to the
  package surface.
- `tests/test_memory_capture_package.py` — D1 identity, boundary, safety,
  isolation, replay, and adapter evidence.

## ROOT CAUSES ADDRESSED

- Manual capture orchestration and CLI behavior lived in a script rather than
  the package authority boundary.
- Historical and package callers did not have an explicit shared capture
  implementation identity.
- The adapter needed to preserve bare `remember` imports and caller migration
  checks without retaining a second implementation.
- The capture safety policy and `MemoryValidator` had to remain single-object
  legacy bridges instead of being copied into a second authority.

## CANONICAL WRITE CONTRACT

`brain_eleven.memory.capture.remember` performs normalization and the safety
check, resolves scope through the package scope surface, then delegates the
canonical write to `MemoryValidator.validate_single_and_append`. It does not
instantiate `MemoryStore`, copy transaction/lock logic, or write JSON itself.
The validator continues to own the existing `MemoryStore.transact` boundary.

Manual `remember()` remains an explicit action and therefore does not invoke
the proactive opt-in gate. The proactive policy helpers continue to use
`ProjectRegistry` and fail closed for unregistered, disabled, or archived
projects. The derived entity graph is rebuilt only after a new canonical
record; duplicate capture returns the existing record without a revision or
graph rebuild.

## BEHAVIORAL NOTE

The migration changes implementation location only. Scope, project identity,
registry relocation, duplicate fingerprinting, safety rejection ordering,
CLI options, and direct-execution behavior are preserved. Absolute project
roots remain resolution inputs and are not persisted as canonical project
metadata.

## TESTS ADDED

`tests/test_memory_capture_package.py` covers:

- package/adapter/bare-module function, validator, and safety object identity;
- adapter-only AST and no direct JSON/`MemoryStore` write path;
- absence of copied transaction authority;
- same-project duplicate no-op revision and no graph rebuild;
- concurrent replay producing one canonical record;
- cross-project isolation and absolute-root non-persistence;
- safety rejection before registry access;
- `remember_opt_in.py` package-surface identity.

## TESTS EXECUTED

- Focused D1 + unchanged remember/safety suites: **34 passed**.
- Full repository suite at the exact implementation head: **936 passed, 2
  warnings** in 174.19s.
- Critical flake8 (`E9,F63,F7,F82`) on changed production/tests: **PASS**.
- `compileall` for changed production/tests: **PASS**.
- `git diff --check`: **PASS**.
- Clean interpreter package/adapter identity sanity: **PASS**.

The two warnings are pre-existing FastAPI/Starlette dependency deprecations.

## SAFETY METRICS

- New canonical authorities: **0**.
- Direct capture JSON/file writes in adapter: **0**.
- Safety rejection before registry/persistence: **verified**.
- Same-project duplicate revision churn: **0**.
- Concurrent replay duplicate canonical records: **0**.
- Cross-project duplicate suppression leakage: **0** in focused and existing
  coverage.
- Absolute project-root leakage into canonical record: **0** in focused test.

## KNOWN LIMITATIONS / OPEN FAILURES

- `capture_safety.py` and `memory-validator.py` remain legacy implementation
  modules behind the shared loader by contract; this package does not rewrite
  either authority.
- Native client trust and remote CI evidence are outside this bounded D1
  package and remain governed by their existing IG gates.
- No new P0/P1 failure was found. Independent byte-diff and review are still
  pending.

## INDEPENDENT REVIEW

**REVIEW PENDING.** The implementation is intentionally not self-accepted and
no `SHIP` verdict is claimed here. Independent review must verify the
canonical write boundary, identity, scope/safety behavior, and the exact-head
evidence before D1 is closed.

## SCORE BEFORE / AFTER

- Capture runtime/package authority: **not rescored before independent review**.
- Intelligence, retrieval, and Phase 20 status: **unchanged**.

## VERDICT

**REVIEW PENDING** — D1 implementation and evidence are complete for review;
independent acceptance is required before the next Slice 2D package.
