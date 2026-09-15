# TSC-02 — Project Identity and Registry-Lineage Package Report

**PACKAGE:** TSC-02
**REVISION:** `b2e80d0cd7f21ff7a960ceeaaace8eac608526a0` (implementation and
focused-test revisions: `5083bcf`, `f69ac0e`, `b2e80d0`)
**BASELINE:** `4bf07478db02002971ad108192c553a9beb35967`
**PROGRAM:** Engineering Weak-Point Improvement Goal
**PHASE 20:** FROZEN / LOCKED
**V2 RUNTIME:** SHADOW

## OBJECTIVE

Make a composed `TaskStateContext` prove the project and registry root for
which it was created before Router or Authority can deliver project-scoped
context. The bounded change adds content-free opaque root identity and
registry revision lineage, revalidates it around cache use, and rejects root
reuse and registry races without changing canonical persistence authorities.

## FILES CHANGED

- `brain_eleven/projects/identity.py` — new read-only, domain-separated root
  identity and registry-lineage validator.
- `brain_eleven/projects/__init__.py` — package exports for the shared
  identity surface.
- `scripts/task_state_context.py` — two-phase registry revalidation and the
  explicit lineage envelope; the legacy module remains the implementation
  authority for this package.
- `context_router/router.py` — lineage validation before cache lookup,
  after cache lookup, before delivery and before cache store.
- `authority/resolver.py` — independent lineage validation at the same
  cache/evidence boundaries.
- `authority/serialization.py` — strict lineage encode/decode checks.
- `tests/test_tsc02_identity.py` — focused identity, race, serialization,
  isolation and privacy evidence.
- `WEAKNESS-TSC-02-IDENTITY-PACKAGE-REPORT.md` — this evidence report.

No `runtime/context.py`, `MemoryStore`, `StateStore`, `ProjectRegistry`
persistence implementation, retrieval/V2 path, eval labels, holdout inputs or
Phase 20 file was changed.

## ROOT CAUSES ADDRESSED

- A context previously carried project/state data without an opaque identity
  for the normalized root occupying that project registry record.
- Compose-time task and state reads could straddle a registry mutation.
- Router and Authority could reach cache lookup or cached delivery without an
  independent current-root/registry check.
- Serialized current-project context could omit lineage and silently enter a
  current-project path.

## IMPLEMENTATION NOTES

- `project-root-v1:<64 lowercase hex characters>` is derived from a
  domain-separated SHA-256 digest of the normalized registry root. Raw roots
  are never placed in new lineage fields or lineage errors.
- The existing outer schema number remains `1` under an explicit
  schema-1-with-required-lineage policy. A schema-1 current-project payload
  without `lineage` is rejected; unresolved and global contexts use explicit
  project-free status forms.
- The composer reads a registry snapshot before task/state resolution and
  re-reads it before publishing. Project ID, normalized root and registry
  revision must agree. Router and Authority conservatively treat any registry
  revision change as stale and revalidate around cache operations.
- The final small follow-up (`b2e80d0`) reuses the already validated snapshot
  identity instead of recomputing the root digest in the composer.

## TESTS ADDED

`tests/test_tsc02_identity.py` contains 11 focused tests covering:

- opaque fixed-format identity and path privacy;
- composer lineage shape and field order;
- valid relocation with stable project ID and a new root identity;
- root reuse rejection in Router and Authority with zero candidates;
- compose-time registry race detection;
- strict serialization round-trip, missing-lineage rejection, raw-path and
  project-mismatch rejection;
- explicit unresolved/global project-free forms;
- validation before Router cache lookup;
- Router cache race rejection;
- Authority cache race rejection.

## TESTS EXECUTED

All commands used the repository `.venv` interpreter.

- Exact baseline focused suite at `4bf0747` — **150 passed**.
- TSC-02 focused suite at final implementation revision —
  `tests/test_tsc02_identity.py`, `tests/test_task_state_context.py`,
  `tests/test_context_router.py`, `tests/test_authority_resolver.py`,
  `tests/test_context_compiler.py`, `tests/test_phase14_scope.py`,
  `tests/test_task_model.py`, `tests/test_pre12_memory_state_caller_migration.py`
  — **161 passed**.
- `python -m pytest tests -q` at exact revision `f69ac0e` after the bounded
  implementation/test commits — **1365 passed, 4 skipped, 2 warnings** in
  294.51 seconds. The final `b2e80d0` change is covered by the focused
  composition tests above.
- Critical flake8:
  `python -m flake8 --select E9,F63,F7,F82 authority/resolver.py
  authority/serialization.py brain_eleven/projects/__init__.py
  brain_eleven/projects/identity.py context_router/router.py
  scripts/task_state_context.py tests/test_tsc02_identity.py` — **passed**.
- `python -m compileall -q` on all changed Python files — **passed**.
- `git diff --check` — **passed**.
- `python -m evals.task_state_eval --suite smoke/public/holdout` at the
  post-implementation revision — all three suites **passed** (exit code 0).
  Their reports were byte-equal to the baseline reports:
  `smoke_report_equal=true`, `public_report_equal=true`,
  `holdout_report_equal=true`.
- Frozen input hashes for `evals/task_state_eval.py` and the existing task,
  router, authority, compiler, scope and migration test surfaces all matched
  the baseline. No eval labels, thresholds or holdout fixtures were tuned.

## QUALITY METRICS BEFORE

The TSC review estimated the task-state surface at approximately **6.5/10**
and context composition at **7.0/10**. The root-reuse lineage failure was
reproducible; the existing task-state evaluation suites passed but did not
measure that identity failure.

## QUALITY METRICS AFTER

The bounded root-reuse, relocation, compose-race, cache-race, serialization
and isolation behaviors are now executable and passing at the exact revision.
The broader task-state/context score is **not rescored here**; no unsupported
aggregate intelligence or daily-use score increase is claimed pending
independent implementation review.

## SAFETY METRICS

- Root reuse: stale context returns bounded `STALE_INPUT` with zero Router and
  Authority candidates.
- Relocation: old context is stale; a new context retains the stable project
  ID and receives a different opaque root identity.
- Registry races: compose, Router and Authority race tests reject stale input;
  stale cache entries are not delivered or stored.
- Isolation: task/state project IDs must agree with lineage; unresolved/global
  forms cannot be widened into project routes.
- Privacy: new lineage and lineage errors contain no raw root, registry
  document, memory content or traceback text. The historical
  `TaskEnvelope.request.raw` field remains unchanged.
- Authority: no MemoryStore, StateStore or ProjectRegistry write path was
  introduced; existing locking/CAS and scope checks remain in place.
- Evaluation safety: frozen smoke/public/holdout reports and input hashes are
  unchanged.

## KNOWN LIMITATIONS

- The package uses the explicit schema-1-with-required-lineage policy rather
  than changing the outer schema number. A future schema change requires a
  separate contract and versioned fixtures.
- `scripts/task_state_context.py` remains the legacy implementation surface;
  its Slice 2F package inversion is out of scope.
- Validation is intentionally conservative: an unrelated registry revision
  change also invalidates an older project context.
- Native client trust/latency and W-07B dogfood remain separate work.

## OPEN FAILURES

No failure was observed within the bounded TSC-02 focused or full regression
surfaces. Implementation acceptance remains open until an independent
read-only implementation reviewer checks the contract, diff, race ordering,
privacy and authority boundaries.

## INDEPENDENT REVIEW

The **contract** was independently reviewed and accepted as `SHIP` at
`90fd416` for contract revision `62dfedf`. The implementation has not been
independently reviewed in this report. Self-review is not acceptance.

## SCORE BEFORE

- Task-state surface: approximately **6.5/10**.
- Context composition: approximately **7.0/10**.

## SCORE AFTER

**Not rescored pending independent implementation review.** The focused
identity and lineage evidence is green; broader intelligence and daily-use
quality are unaffected claims for this bounded package.

## VERDICT

**REVIEW PENDING** — this package intentionally does not self-ship.
