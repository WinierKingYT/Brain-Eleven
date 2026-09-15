# TSC-01 — Timezone-Bound State Resolution Contract

**Status:** CONTRACT / IMPLEMENTATION NOT AUTHORIZED  
**Program:** Engineering Weak-Point Improvement Goal  
**Baseline revision:** `b2830c5968b51f21426a754270dae244d6fc70de`  
**Phase 20:** FROZEN / LOCKED  
**V2 runtime:** SHADOW

## 1. Problem and objective

The read-only state resolver accepts an ISO-8601 timestamp without an explicit
timezone. `scripts/state_store.py:_timestamp` currently validates the string
with `datetime.fromisoformat`, and `scripts/state_resolver.py:_parse_timestamp`
returns the resulting naive `datetime`. `StateResolver.resolve` then subtracts
that value from its aware UTC clock (`_utc_now`), which raises Python's
`TypeError: can't subtract offset-naive and offset-aware datetimes`. The
exception escapes `TaskStateComposer.compose` and can turn the native context
path into a generic failure.

This package makes temporal input behavior explicit and bounded. A state
record with an ambiguous timestamp must never crash the resolver, silently
assume a timezone, or produce a freshness value that looks valid. The fix is
limited to timestamp validation and the resolver's bounded corruption mapping;
it does not change task analysis, project identity, serialization lineage,
retrieval or canonical authority design.

## 2. Bounded implementation surface

Only these files may change:

- `scripts/state_store.py` — tighten `_timestamp` so persisted state accepts
  only parseable ISO-8601 values with an explicit UTC offset (`Z` or
  `+/-HH:MM`). The existing schema exception and transaction/backup behavior
  remain unchanged.
- `scripts/state_resolver.py` — keep `_utc_now` aware, make timestamp parsing
  reject naive values, and map persisted timestamp parse/type failures to the
  existing `STATE_CORRUPT` read-only result with a bounded, content-free error.
  No automatic rewrite or timezone assumption is allowed.
- Focused tests and the package evidence/report documents.

The package must not change `scripts/task_state_context.py`,
`brain_eleven/runtime/context.py`, `authority/serialization.py`, project
registry behavior, MemoryStore/StateStore authority boundaries, retrieval,
hooks, V2 or Phase 20. If a runtime caller needs a compatibility change beyond
the bounded resolver mapping, stop and report `RETHINK` rather than widening
this package.

## 3. Temporal contract

1. **Accepted persisted value:** a non-empty string accepted by
   `datetime.fromisoformat` after the existing `Z` → `+00:00` handling, with
   `tzinfo` and a non-`None` `utcoffset()`. The stored representation is not
   rewritten.
2. **Rejected persisted value:** missing, non-string, malformed, or timezone-
   naive `updated_at`. `StateService` must reject it before any canonical
   write; a pre-existing malformed record must resolve as `STATE_CORRUPT`.
3. **Freshness:** age is computed only between aware datetimes. Offset-bearing
   values are compared correctly; no local-machine timezone is consulted.
4. **Bounded error:** the corruption result may expose a stable error code or
   short field-level message, but must not expose the raw timestamp, state
   document, filesystem path, prompt, memory content or traceback.
5. **No effect:** reading malformed state creates no registry, state, memory,
   graph or context write and does not advance a revision.
6. **Caller clock:** existing callers that pass `now` must continue to use an
   aware `datetime`. A newly introduced silent assumption for a naive caller is
   forbidden; if a separate caller bug is discovered, record it as an open
   finding instead of changing this contract.

## 4. Invariants

- `STATE_AVAILABLE`, `STATE_NOT_FOUND`, `PROJECT_UNKNOWN`,
  `PROJECT_ARCHIVED`, `STATE_UNAVAILABLE` and `STATE_CORRUPT` keep their
  existing meanings for valid inputs.
- Valid state IDs, revisions, record ordering, scope and project isolation are
  byte/parity unchanged.
- The resolver remains read-only. It does not repair or rewrite a malformed
  state document.
- `MemoryStore`, `ProjectRegistry` and `StateStore` remain the only canonical
  authorities; no second persistence path is introduced.
- Existing lock, CAS, backup, and atomic-write behavior is untouched.
- `TaskStateComposer` receives an explicit state result rather than an
  uncaught timezone `TypeError`; no raw state content crosses the runtime
  context boundary.

## 5. Required evidence and tests

### 5.1 Focused behavior

Add tests proving all of the following without changing existing tests:

- `StateService` rejects a naive `updated_at` before writing and leaves the
  state file and revision unchanged.
- A manually seeded naive or malformed state resolves to `STATE_CORRUPT`
  without an uncaught `TypeError` and without raw timestamp content in the
  error.
- `Z`, positive-offset and negative-offset timestamps resolve successfully
  and produce deterministic freshness at an aware reference time.
- `TaskStateComposer.compose` and the native `compile_context` boundary expose
  the bounded corruption outcome for malformed state; they do not write a
  memory, registry, graph or context projection as a side effect.
- Existing valid-state behavior remains unchanged.

### 5.2 Verification gates

1. Exact baseline and implementation revision are recorded with
   `git rev-parse HEAD`.
2. Focused state/resolver/task-context/runtime tests pass, including the
   existing 38-test state/context suite.
3. Full `pytest tests -q` passes with existing warnings identified.
4. Critical flake8 (`E9,F63,F7,F82`), `compileall` and `git diff --check`
   pass on every changed Python file.
5. A read-only independent reviewer checks the diff, exception mapping,
   no-write behavior, privacy and scope boundaries. Self-review is not an
   acceptance verdict.

## 6. Acceptance and failure policy

The package can be marked `SHIP` only when every required test and verification
gate passes and independent review returns exactly `SHIP`. An uncaught naive
timestamp exception, silent UTC assumption, raw-content error, revision/write
side effect, or regression is `FIX-FIRST`. Any need to modify identity lineage,
serialization, task-state callers or canonical authorities is `RETHINK` and
requires a new contract.

This package does not close TSC-02 project identity/registry lineage, TSC-03
strict serialized-state decoding, task_state_context package inversion or the
W-07B native trust gates.

## 7. Package report template

```text
PACKAGE: TSC-01
REVISION: <exact implementation/review SHA>
OBJECTIVE: <bounded timezone validation and corruption mapping>
FILES CHANGED: <exact paths>
ROOT CAUSES ADDRESSED: <naive/aware timestamp mismatch>
TESTS ADDED: <focused tests>
TESTS EXECUTED: <commands and exact results>
QUALITY METRICS BEFORE: <state/context score and failure evidence>
QUALITY METRICS AFTER: <evidence-backed result>
SAFETY METRICS: <no-write, privacy, scope and revision results>
KNOWN LIMITATIONS: <explicit caller/legacy constraints>
OPEN FAILURES: <none or exact failures>
INDEPENDENT REVIEW: <SHIP / FIX-FIRST / RETHINK, exact review SHA>
SCORE BEFORE: <context/task-state score>
SCORE AFTER: <evidence-backed score, no unsupported increase>
VERDICT: <SHIP / FIX-FIRST / RETHINK>
```

**Plan status: REVIEW PENDING — implementation has not started.**
