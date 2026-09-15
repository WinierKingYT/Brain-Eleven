# TSC-01 — Timezone-Bound State Resolution Package Report

**PACKAGE:** TSC-01  
**REVISION:** `9bb24d8c3a5ff3595975f26fc1b826c114ba1314`  
**STATUS:** REVIEW PENDING — implementation and verification are complete; independent acceptance has not been performed.  
**Phase 20:** FROZEN / LOCKED  
**V2 runtime:** SHADOW

## OBJECTIVE

Make persisted state timestamps explicitly timezone-aware and prevent a
malformed or naive timestamp from escaping the resolver as an uncaught
naive/aware `TypeError`. The change preserves valid offset behavior and keeps
the existing StateStore/StateService authority, locking, revision, backup and
atomic-write paths intact.

## FILES CHANGED

- `scripts/state_store.py` — `_timestamp` now requires a parsed timestamp to
  have both `tzinfo` and a non-`None` UTC offset.
- `scripts/state_resolver.py` — `_parse_timestamp` rejects missing, malformed
  and naive values; StateStore corruption and unavailable-store errors are
  mapped to stable, content-free messages; invalid timestamp data returned by
  a lower-level/custom store is mapped to `STATE_CORRUPT`.
- `tests/test_tsc01_timezone.py` — focused write, resolver, privacy and
  composer evidence.
- `WEAKNESS-TSC-01-TIMEZONE-PACKAGE-REPORT.md` — this report.

No `task_state_context.py`, native `compile_context`, serialization, registry,
memory, retrieval, hook, W-07B or Phase 20 file was changed.

## ROOT CAUSES ADDRESSED

- `_timestamp` previously accepted timezone-naive ISO values into canonical
  state documents.
- `_parse_timestamp` previously returned a naive `datetime`, while freshness
  calculation used an aware UTC clock.
- `StateResolver` previously exposed path-bearing `StateStoreCorrupt` and
  `OSError` text and did not catch timestamp parsing failures after a lower
  layer returned state.

## TESTS ADDED

`tests/test_tsc01_timezone.py` adds nine tests covering:

- rejection of a naive mutation before persistence, with unchanged bytes,
  revision and backup;
- `Z`, positive-offset and negative-offset timestamps without rewriting;
- seeded naive and malformed documents producing bounded `STATE_CORRUPT`;
- a lower-level bypass returning a naive state without an uncaught `TypeError`;
- sanitization of a path-bearing corruption exception;
- bounded `TaskStateComposer` behavior with no filesystem side effect.

## TESTS EXECUTED

All commands used the repository `.venv` interpreter.

- `python -m pytest tests/test_tsc01_timezone.py -q` — **9 passed**
- Existing state/context suite:
  `python -m pytest tests/test_task_state_context.py tests/test_state_resolver.py tests/test_context_router.py tests/test_authority_resolver.py -q`
  — **38 passed**
- Extended state/boundary regression including the focused tests — **61 passed**
- `python -m pytest tests -q` at the exact revision above — **1354 passed, 4 skipped, 2 warnings**
- `python -m flake8 --select E9,F63,F7,F82 scripts/state_store.py scripts/state_resolver.py tests/test_tsc01_timezone.py` — **passed**
- `python -m compileall -q scripts/state_store.py scripts/state_resolver.py tests/test_tsc01_timezone.py` — **passed**
- `git diff --check` — **passed**

The two full-suite warnings are pre-existing dependency deprecations from
Starlette/httpx and AnyIO.

## QUALITY METRICS BEFORE

The read-only TSC audit scored the task-state surface approximately **6.5/10**
and context composition **7.0/10**. Scope/authority safety was estimated at
**7.5–8.0/10**. The P1 timezone failure was reproducible as an uncaught
naive/aware subtraction error.

## QUALITY METRICS AFTER

The bounded failure is covered and no longer escapes the resolver: malformed
state produces `STATE_CORRUPT`, while valid `Z`, `+03:00` and `-02:00`
timestamps preserve their exact stored representation and resolve with
deterministic freshness. The existing suite remains green. The broader
task-state/context score is **not increased before independent review** and
remains provisionally **6.5–7.0/10**.

## SAFETY METRICS

- Naive write: **no canonical file-byte change, no revision increment, no
  backup change**.
- Malformed read: **no state, registry, memory or graph write**.
- Resolver corruption errors: **no filesystem path, raw timestamp, state
  document, exception representation or traceback** in the returned top-level
  error.
- Valid offset semantics: **preserved**, including the original string form.
- Canonical authority and lock/CAS/backup boundaries: **unchanged**.
- Cross-project scope and lifecycle behavior: **unchanged**.

## KNOWN LIMITATIONS

This package deliberately does not address TSC-02 project identity/registry
lineage, TSC-03 strict nested state decoding, the `task_state_context.py`
package inversion, or native `compile_context` error translation. The caller
clock contract still requires callers that pass `now` to provide an aware
`datetime`; this package does not silently infer a timezone for a naive caller.

## OPEN FAILURES

- No bounded TSC-01 P0/P1 failure remains after the exact-head verification.
- Independent read-only review is still required; this report does not grant
  acceptance and does not mark the package `SHIP`.

## INDEPENDENT REVIEW

**PENDING.** A separate read-only reviewer must inspect the exact revision,
exception mapping, no-write evidence, privacy boundary and scope. Self-review
is not an acceptance verdict.

## SCORE BEFORE

Task-state/context surface: **6.5–7.0/10** (audit estimate).

## SCORE AFTER

**Not re-scored pending independent review.** The focused behavioral evidence
improves the measured timezone failure mode, but no unsupported aggregate score
increase is claimed.

## VERDICT

**REVIEW PENDING — do not treat as SHIP until independent review returns exactly
`SHIP`.**

