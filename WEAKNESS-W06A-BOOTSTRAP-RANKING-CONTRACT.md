# W-06A Contract — V1 SessionStart Bootstrap Ranking

**Status:** BOUNDED CONTRACT / IMPLEMENTATION PENDING  
**Program:** Engineering Weak-Point Improvement Goal  
**Priority:** P1 product quality  
**Target:** `scripts/context-compiler.py` V1 bootstrap ranking  
**Phase 20:** FROZEN / LOCKED  
**V2 runtime:** SHADOW

## Problem

The active SessionStart bootstrap path calls
`ContextCompiler._rank_memories(limit=5)`. Its score currently combines only
memory type priority, quality and freshness. The compiler has already resolved
the requested project's `CurrentProjectState`, but objective, active blockers,
requirements, work items, constraints and risks do not influence which five
memories are selected. Equal scores also preserve input order, which can make
the result depend on the on-disk list order rather than a documented stable
tie-break.

This is a bounded V1 bootstrap quality issue. It is not evidence that the V2
task-aware retrieval path should be promoted or rewritten.

## Scope

The package may change only the V1 ranking implementation and its focused
tests. It must:

1. preserve the existing project-scope filter and current-project-first tier;
2. keep the existing no-query ranking behavior compatible for callers that do
   not provide task/state text;
3. derive a deterministic, bounded query from the already-resolved current
   project state when SessionStart has one, using only structured fields such
   as objective, phase, active blockers, requirements, work items, constraints
   and risks;
4. add an explicit, explainable lexical relevance component for that query;
5. use a documented formula and deterministic secondary keys so equal scores do
   not depend on input/file order;
6. keep inactive-memory filtering, approval filtering, safety checks, budget
   trimming, lineage checks and output schema unchanged;
7. fail soft on malformed optional memory fields or unavailable state without
   widening scope or injecting untrusted data.

The ranking signal must remain deterministic and local. No model, embedding
provider, network call or new persistence authority is allowed.

## Proposed ranking contract

When no state/query text is available, retain the current weighted behavior:

```
score = 0.40 * type_priority + 0.40 * quality + 0.20 * freshness
```

When bounded state/query text is available, use the same signals with the
following fixed, normalized weights:

```
score = 0.30 * type_priority + 0.30 * quality + 0.15 * freshness
        + 0.25 * lexical_relevance
```

These weights are a bounded V1 contract, not a holdout-tuned claim. Scope tier
remains the primary sort key. The remaining keys must include descending score
and a stable memory identity (`memory_id`/`id`, with a deterministic content
fallback when absent).

Lexical matching must use normalized text tokens and must not treat a memory's
filesystem path or unrelated vault content as query input. A missing or
malformed optional field receives a safe fallback and never aborts bootstrap.

## Invariants

- Project isolation and `filter_memories` semantics remain unchanged.
- Global/project/default/all retrieval-scope rules remain unchanged.
- Inactive (`superseded`, `resolved`, or other non-`active`) memories remain
  excluded.
- `compile_bootstrap` continues to be V1, read-only, bounded by the existing
  token budget and revalidated against canonical memory/state revisions.
- No canonical MemoryStore, StateStore or ProjectRegistry write path is added.
- `brain_eleven/runtime/context.py`, V2 routing/authority/compiler code,
  embedding providers and Phase 20 remain unchanged.
- The same input set yields the same selected order regardless of input list
  permutation or filesystem ordering.

## Acceptance evidence

- A fixed state/query case selects a task-relevant memory ahead of a recent but
  unrelated memory when other signals are held equal.
- Equal-score memories have a stable, documented identity tie-break across
  repeated runs and input permutations.
- Existing no-query type-priority, freshness, inactive-filter and scope tests
  pass without changing their assertions.
- State-derived query construction is bounded and tested for objective,
  blocker, constraint and malformed/empty state cases.
- Malformed timestamp, quality, type and content fields remain fail-soft.
- V1 bootstrap output schema, safety filtering, budget handling and lineage
  checks remain unchanged.
- Existing `tests/test_context_compiler.py`, runtime context/bootstrap tests,
  scope/privacy tests and the full suite pass.
- Critical flake8 (`E9,F63,F7,F82`), compile/import sanity and
  `git diff --check` pass.
- An independent read-only reviewer returns exactly `SHIP`, `FIX-FIRST` or
  `RETHINK`; the implementer must not self-accept the package.

## Out of scope

No V2 promotion, task-aware retrieval rewrite, embedding or semantic-provider
change, extraction/correction change, canonical persistence change, capture
worker change, reminder redesign, architecture migration, Phase 20 work or
holdout threshold/tuning change is permitted.

## Package report fields

`PACKAGE`, `REVISION`, `OBJECTIVE`, `FILES CHANGED`, `ROOT CAUSES ADDRESSED`,
`TESTS ADDED`, `TESTS EXECUTED`, `QUALITY METRICS BEFORE/AFTER`, `SAFETY
METRICS`, `KNOWN LIMITATIONS`, `OPEN FAILURES`, `INDEPENDENT REVIEW`, `SCORE
BEFORE/AFTER`, `VERDICT`.

**Package verdict:** REVIEW PENDING until implementation and independent review.
