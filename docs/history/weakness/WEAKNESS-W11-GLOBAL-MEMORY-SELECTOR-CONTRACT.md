# W-11 — W06B Global Memory Selector Contract

**Status:** CONTRACT / IMPLEMENTATION NOT AUTHORIZED

**Program boundary:** Engineering Weak-Point Improvement Goal

**Phase 20:** FROZEN / LOCKED

**V2 runtime:** SHADOW

## Problem

`brain_eleven/runtime/task_aware.py::select` receives the legacy compiler's
already scoped records, but its filter currently accepts a global record only
when `record.get("project_id") is None`. The canonical scope normalizer in
`scripts/memory_scope.py::infer_memory_scope` represents a global record as
`(scope="global", project="", project_id="")`. Such records are therefore
silently omitted from the opt-in `W06B_TASK_AWARE` selector. This is a P2
retrieval correctness defect in an opt-in path; it does not authorize V2
promotion or any Phase 20 work.

## Objective

Make W06B selection use the canonical scope semantics so that:

- global records represented by empty, missing, or legacy project fields are
  eligible when global retrieval is enabled;
- project-scoped records are eligible only for the current task project;
- records from another project are never selected;
- the existing ranking, token/byte limits, approval gate, safety checks,
  provider labels, and fallback behavior remain unchanged.

## Bounded implementation

Only `brain_eleven/runtime/task_aware.py` and focused tests may change.
Selection must use the existing package-owned scope interpretation
(`brain_eleven.memory.scope.infer_memory_scope` or an equivalent call to that
canonical surface). It must not duplicate scope normalization rules or write
to MemoryStore/StateStore/ProjectRegistry. No embedding, ranking-weight,
task-model, V2, HOLDOUT, or Phase 20 changes are allowed.

The default `V1_LEGACY` path is out of scope. `W06B_TASK_AWARE` remains an
explicit opt-in retrieval mode and remains rollback-able through the existing
runtime configuration.

## Invariants

1. Global records are eligible regardless of whether their legacy payload has
   `project_id` missing, `None`, or empty, provided the canonical scope is
   global.
2. A project record is eligible only when its canonical project ID equals the
   task project ID.
3. A record carrying a project ID but no valid global scope is not widened into
   global scope.
4. `human_approval=True` continues to exclude unapproved records.
5. `contains_secret` and `evaluate_capture` safety rejection remains before
   rendering; no rejected record reaches context output.
6. `MAX_ITEMS`, token, byte, deterministic ordering, provider/status fields,
   and exception-to-`UNAVAILABLE` behavior remain unchanged.
7. The selector remains read-only and introduces no canonical write or model
   authority path.

## Required evidence

- A regression test proves a canonical global record with `scope="global"`
  and `project_id=""` is selected for a project task.
- A legacy global representation with no project ID remains eligible.
- A project-A record is excluded for project B, while the global record remains
  eligible; the test proves no cross-project leakage.
- Existing `tests/test_w06b_task_aware.py` tests pass unchanged.
- The default V1 path and invalid-mode rollback tests remain unchanged.
- Focused W06B tests, full `pytest tests -q`, critical flake8, compileall, and
  `git diff --check` pass at the exact revision.
- An independent read-only reviewer checks the diff, scope authority, safety
  gates, and no-HOLDOUT/no-V2 boundary.

## Exit gate

The package is `SHIP` only after all required evidence passes and an
independent reviewer returns exactly `SHIP`. Until then the package remains
`REVIEW PENDING`; implementation must not be treated as a retrieval-quality
graduation or V2 promotion.

## Package report template

`WEAKNESS-W11-GLOBAL-MEMORY-SELECTOR-PACKAGE-REPORT.md` must record:

`PACKAGE`, `REVISION`, `OBJECTIVE`, `FILES CHANGED`, `ROOT CAUSES ADDRESSED`,
`TESTS ADDED`, `TESTS EXECUTED`, `QUALITY METRICS BEFORE`,
`QUALITY METRICS AFTER`, `SAFETY METRICS`, `KNOWN LIMITATIONS`,
`OPEN FAILURES`, `INDEPENDENT REVIEW`, `SCORE BEFORE`, `SCORE AFTER`, and
`VERDICT`.

**Contract status:** REVIEW PENDING — implementation not authorized by this
document alone.
