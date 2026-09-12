# W-07A Contract — Native SessionStart Continuity Read

**Status:** BOUNDED CONTRACT / IMPLEMENTATION PENDING  
**Program:** Engineering Weak-Point Improvement Goal  
**Priority:** P2 product continuity  
**Target:** native `brain_eleven/runtime/context.py` V1 bootstrap plus the
existing `scripts/context-compiler.py` state rendering  
**Phase 20:** FROZEN / LOCKED  
**V2 runtime:** SHADOW

## Problem

The legacy shell SessionStart hook prints `Last Session.md` and
`Açık Döngüler.md`, but native SessionStart delivery uses
`brain_eleven.runtime.context.compile_bootstrap()`. That path deliberately
passes empty markdown continuity inputs to the V1 compiler and therefore
surfaces only the top memories plus a partial current state (objective,
blockers and constraints). Canonical active work items, requirements and risks
are not shown to the native user. SessionEnd maintenance writes a report, but
native bootstrap does not have a bounded continuity summary of its own.

This is a read-path continuity gap. It must not be solved by making markdown
files canonical or by writing raw transcript content into them.

## Scope

The package may change only the structured V1 bootstrap rendering and its
focused tests. It must:

1. include bounded, project-scoped structured continuity from the already
   resolved `CurrentProjectState`: active work items, active requirements,
   blockers, constraints and risks, with stable type labels and limits;
2. preserve the existing objective, phase, scope filtering, safety filtering,
   token budget and canonical revision/state lineage checks;
3. make native `compile_bootstrap()` deliver the same bounded structured
   continuity section that the V1 compiler renders, without reading unscoped
   `Last Session.md`, `Threads.md`, `Daily.md` or `Açık Döngüler.md`;
4. keep the current maintenance report path informational and unchanged;
5. fail closed on unavailable/corrupt state through the existing
   `ContextBootstrapError` behavior, and fail soft only for optional malformed
   records that cannot be rendered;
6. keep the output content bounded and deterministic so a large state cannot
   exhaust the hook context budget.

The package is read-only with respect to canonical authorities and companion
files. No new reminder writer, scheduler, worker action or persistence
authority is introduced.

## Invariants

- `MemoryStore`, `StateStore` and `ProjectRegistry` remain the only canonical
  authorities; no write path is added.
- Project-scoped state is rendered only for the resolved project. Global
  memories may remain eligible under the existing retrieval scope, but another
  project's state or work items must never appear.
- Existing native hook response keys, selected-memory IDs, provider identity,
  budget trimming and stale-input checks remain compatible.
- Companion markdown remains manual/legacy and is never silently rewritten.
- V2 routing, authority, compiler, embeddings, capture worker behavior and
  Phase 20 remain unchanged.

## Acceptance evidence

- Native `compile_bootstrap()` contains bounded sections for active work items,
  requirements, blockers, constraints and risks when the resolved state has
  them.
- A second project's state is absent from the first project's bootstrap.
- Empty/not-found state does not fabricate reminders; corrupt/unavailable state
  follows the existing degraded/error contract.
- Record count and text length limits are deterministic and tested.
- Existing V1 context compiler, runtime context, scope/privacy, budget and
  lineage tests pass without changing their existing assertions.
- No `Daily.md`, `Last Session.md`, `Threads.md` or `Açık Döngüler.md` write is
  introduced; maintenance report behavior remains unchanged.
- Critical flake8 (`E9,F63,F7,F82`), compile/import sanity, full regression and
  `git diff --check` pass.
- An independent read-only reviewer returns exactly `SHIP`, `FIX-FIRST` or
  `RETHINK`.

## Out of scope

No automatic markdown reminder writer, transcript summarizer, maintenance
scheduler, capture/worker change, task-aware retrieval rewrite, V2 promotion,
semantic extraction/correction change, canonical schema change, architecture
consolidation or Phase 20 work is permitted.

## Package report fields

`PACKAGE`, `REVISION`, `OBJECTIVE`, `FILES CHANGED`, `ROOT CAUSES ADDRESSED`,
`TESTS ADDED`, `TESTS EXECUTED`, `QUALITY METRICS BEFORE/AFTER`, `SAFETY
METRICS`, `KNOWN LIMITATIONS`, `OPEN FAILURES`, `INDEPENDENT REVIEW`, `SCORE
BEFORE/AFTER`, `VERDICT`.

**Package verdict:** REVIEW PENDING until implementation and independent review.
