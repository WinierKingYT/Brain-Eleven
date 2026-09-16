# W-24 Memory Truth Safety — Independent Implementation Review

**PACKAGE:** W-24
**REVIEW TYPE:** independent, read-only implementation review
**CONTRACT METADATA HEAD:** `1ef38125ecbe3586b83f564dfc0607765b59d5a9`
**SUBSTANTIVE CONTRACT REVISION:** `091e064b0a4e95b6f6fbe4c1cc97932d0d7900f0`
**CONTRACT REVIEW:** `4651173f1118406853f563f96639a8623ea07e1f` — SHIP
**IMPLEMENTATION HEAD REVIEWED:** `23770ba867325d786fe108420166609e7c73b760`
**IMPLEMENTATION COMMITS:** `525b116` (code), `e912f44` (tests), `23770ba` (report)
**PHASE 20:** FROZEN / LOCKED
**V2:** SHADOW

## Scope

This review independently inspected the W-24 contract, the implementation
diff, the focused tests, the worker boundary, package/legacy identity, and the
exact verification evidence. No production code was changed and no existing
user files were staged.

The implementation stays within the declared direct-truth surface:

- `scripts/memory_truth.py`
- `brain_eleven/memory/truth.py`
- `tests/test_memory_truth.py`
- `tests/test_w24_memory_truth_safety.py`

`brain_eleven/runtime/worker.py`, `MemoryStore`, `ProjectRegistry`, capture
safety implementation, queue, extraction, graph, retrieval, evaluation input
and Phase 20 files are unchanged in the reviewed range.

## Verified

- The direct truth path calls the existing shared `capture_safety.evaluate_capture`
  object. No second secret regular expression or direct JSON/file writer was
  added to `scripts/memory_truth.py`.
- Content and lifecycle-note safety checks occur before project registry
  lookup and before the canonical transaction. The tested secret and policy
  limit controls produce bounded decisions without a canonical revision or
  backup effect.
- Project-scoped candidates use the existing registry read authority. Missing,
  archived, disabled and malformed registry states are mapped to bounded
  decisions without registry mutation or fallback to caller identity.
- Global project metadata is rejected and accepted project labels are derived
  from the registry. No filesystem root is persisted by this implementation.
- `TruthCandidate` fields, order, `dataclasses.asdict()` shape and the legacy
  request projection remain unchanged. The worker source and its request-hash
  verifier are byte-unchanged.
- Provenance is kept in a private envelope and an additive receipt field. The
  source/approval values do not bypass commitment, scope, lifecycle or the
  `MemoryStore.transact()` lock/CAS boundary.
- The package surface preserves identity with the bare `memory_truth` loader
  surface, and the shared safety function is the same object.
- The exact reviewed workspace reported **51 focused tests passed** for the
  truth, capture-safety, B1/B2 and W-24 surfaces. The exact full suite reported
  **1391 passed, 4 skipped, 2 warnings** using the repository `.venv`.
- Critical flake8 (`E9,F63,F7,F82`) and compile/import checks passed for the
  changed Python files. The worker source diff is empty.
- A manual worker-shaped accepted control reached one canonical memory with
  the bounded worker provenance and approved commitment, and the unchanged
  worker request hash remained compatible.

## Findings requiring correction

### P1 — Registry preflight breaks exact operation replay after lifecycle change

`MemoryTruthEngine.process()` runs `_preflight()` at
`scripts/memory_truth.py:557-579`. For a project candidate this reads the
current registry and can return an early all-preflight result at
`:581-597`. The existing operation receipt is consulted only later inside the
`MemoryStore.transact()` callback at `:600-617`.

I reproduced this with an isolated vault: a project candidate was committed
with an operation ID, the project was then archived, and the identical
operation was replayed. The replay returned `DEGRADED / PROJECT_ARCHIVED`
with no receipt result instead of returning the original receipt/effect as an
idempotent replay. The canonical record was not duplicated, but the operation
contract is still violated and a retry can be reported as a new policy
failure after its effect already exists.

The fix must preserve safety preflight while making an already matching
operation receipt authoritative for replay inside the canonical transaction.
Changed request or provenance identity must still return the existing replay
mismatch, and a new operation must still obey current registry policy. Add a
regression test for archive/disable or registry removal between first commit
and replay.

### P1 — Required worker and failure evidence is incomplete

The W-24 contract requires an explicit accepted worker/B1 control, canonical
effect verification and replay, a direct privileged-boundary distinction,
simulated registry read `OSError`, lifecycle `RESOLVE_EXISTING` note safety,
blank/invalid provenance and non-boolean approval cases, and global
`project_id` coverage. `tests/test_w24_memory_truth_safety.py` contains the
unapproved worker control at `:362-369`, but it does not exercise the accepted
ReviewStore-to-`approved=True` transition, the canonical worker verifier
replay, or the direct privileged distinction. It also does not cover several
of the explicitly required negative cases above.

The package report describes “worker-transition” and broad provenance
coverage, but the committed test surface does not provide those required
proofs. Existing broader runtime tests cover some worker behavior, yet they do
not replace the contract-specific provenance and replay assertions. This gate
must be completed before W-24 can be accepted.

### P2 — Preflight-only rejection loses the public revision lineage

When every candidate is rejected during `_preflight()`, the early return at
`scripts/memory_truth.py:581-597` constructs `TruthResult` with both
`source_memory_revision` and `produced_memory_revision` set to `None`.
Before W-24, a rejected dry-run or no-change commit went through the existing
store read/transaction path and returned the current revision in both fields.
For example, an unregistered project on a fresh vault now returns
`SUCCESS`/`DEGRADED` with null revisions. This is a compatibility regression
in the public result lineage, even though no canonical write occurs. Add an
explicit regression test and preserve the bounded no-write behavior while
reporting the current revision where it is safe and available; keep the
unavailable-registry path's documented no-load behavior.

### P2 — Exact diff check is not green at the claimed verification head

`git diff 4651173..23770ba --check` reports a new blank line at EOF in
`WEAKNESS-W24-MEMORY-TRUTH-SAFETY-PACKAGE-REPORT.md:154`. The package report
records `git diff --check: PASS`, so that evidence claim is not reproducible
at the exact reviewed head. Remove the trailing blank line and rerun the
exact check.

## Deferred boundary items accepted

- Direct API/CLI callers remain a documented trusted privileged boundary; W-24
  does not authenticate a process or prove a ReviewStore token there.
- The caller-supplied `NEW` memory-ID collision remains the explicitly deferred
  W-24A P2 and is not silently counted as fixed.
- No V2 promotion, retrieval tuning, architecture rewrite, worker change,
  capture redesign or Phase 20 work is included.

## Decision

**FIX-FIRST**

The safety, scope, provenance sidecar and canonical transaction boundaries are
substantially aligned with the contract, and the full regression is green.
The exact replay regression, mandatory evidence gaps and failed diff-check
gate leave W-24 open. This review does not modify the implementation and does
not grant SHIP.
