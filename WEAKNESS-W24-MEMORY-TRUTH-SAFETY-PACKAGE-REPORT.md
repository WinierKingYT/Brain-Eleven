# W-24 Direct Memory Truth Safety and Provenance Package Report

**PACKAGE:** W-24

**CONTRACT REVISION:** substantive `091e064b0a4e95b6f6fbe4c1cc97932d0d7900f0`

**CONTRACT METADATA HEAD:** `1ef38125ecbe3586b83f564dfc0607765b59d5a9`

**CONTRACT REVIEW:** `4651173f1118406853f563f96639a8623ea07e1f` — SHIP

**AUDIT BASELINE:** `0ad5fe5d118c03df1d8b0e0a258e2dadf13f5b8b`

**PRE-IMPLEMENTATION HEAD:** `4651173f1118406853f563f96639a8623ea07e1f`

**IMPLEMENTATION REVISION:** code `525b116`; tests `e912f44`

**EXACT VERIFICATION HEAD:** `e912f44b50ccac3ebf87f8c93d748ea2970f031d`

**OBJECTIVE:** Apply the shared capture-safety policy, registered project
authority and derived provenance to the direct `MemoryTruthEngine` path while
preserving the public candidate shape, operation request hash, worker boundary,
canonical transaction boundary and existing lifecycle semantics.

## Files changed

- `scripts/memory_truth.py` — shared safety preflight, registry authority,
  mapping-only provenance sidecar, explicit legacy request projection and
  receipt provenance comparison.
- `brain_eleven/memory/truth.py` — re-export of the stable request projection
  helper; existing identity-preserving adapter remains in place.
- `tests/test_memory_truth.py` — existing synthetic project fixtures now create
  the active registry authority required by the W-24 contract; the old short
  secret control uses a shared-policy secret class.
- `tests/test_w24_memory_truth_safety.py` — focused safety, scope, provenance,
  replay, identity, worker-transition and CLI evidence.

No `MemoryStore`, `StateStore`, `ProjectRegistry`, worker, capture-safety
implementation, queue, review, extraction, graph or retrieval implementation
was changed.

## Root causes addressed

- The direct truth path used a private assignment regex instead of the shared
  `capture_safety.evaluate_capture()` object.
- Project-scoped truth accepted any non-empty project ID without reading the
  canonical registry status and proactive-capture policy.
- Global truth could carry project metadata and `_new_record()` persisted it.
- Lifecycle notes were written without the shared safety gate.
- `_new_record()` used fixed `source="extraction-v2"` and
  `is_approved=True` values.
- Receipt request identity was made explicit through the ordered pre-W-24
  field projection; new provenance is carried only by an additive receipt
  `provenance_hash`.

## Tests and verification

### Baseline

At exact pre-implementation head `4651173`:

- Existing truth, capture-safety, B1 and B2 focused suite: **29 passed, 2
  warnings**.
- The contract baseline probe recorded six shared-policy secret families that
  the direct path classified as `NEW`, while the old private regex happened to
  reject two assignment-shaped controls. An unregistered project commit also
  produced one canonical memory. Source and approval were fixed literals in
  the new record path.

### Tests added

- **25 focused W-24 test cases** in `tests/test_w24_memory_truth_safety.py`.
- Coverage includes all eight shared secret classes, lifecycle-note safety,
  size/line/transcript limits, negative and unavailable registry states,
  global metadata, registry-owned labels, provenance/approval gates, legacy
  candidate field order and `asdict()` shape, old/new receipt replay,
  provenance mismatch, worker unapproved transition, identity and CLI parity.

### Focused after verification

- Truth, capture-safety, worker/B1/B2 and W-24 focused tests: **54 passed, 2
  warnings**.
- Additional capture-closure/runtime regression slice: **170 passed, 2
  warnings**.

### Exact full verification

Using the repository `.venv` interpreter at exact head `e912f44`:

- `python -m pytest tests -q`: **1391 passed, 4 skipped, 2 warnings**.
- Critical flake8 (`E9,F63,F7,F82`) on all changed Python files: **PASS**.
- `compileall` on changed Python files: **PASS**.
- `git diff --check`: **PASS**.

The worker source remained unchanged. Existing worker/B1 capture-closure tests
therefore exercised the historical request-hash verifier against the new
receipt shape; the additive provenance field did not alter `request_hash`.

## Quality and safety metrics

| Metric | Before | After focused evidence |
|---|---:|---:|
| Shared secret bypasses | 6 observed | 0 |
| Unregistered project canonical effects | 1 observed | 0 |
| Archived/disabled project effects | not guarded | 0 |
| Lifecycle-note secret effects | unguarded path | 0 |
| Global project metadata effects | possible/invalid at write boundary | 0 |
| Hardcoded source/approval values | 2 literals | 0 |
| Rejected-candidate canonical writes | not bounded by preflight | 0 |
| Registry-unavailable path leaks | collapsed/unspecified | bounded `SCOPE_ERROR` mapping |
| Public `TruthCandidate` fields changed | 0 | 0 |
| Worker legacy `request_hash` changes | 0 | 0 |

Diagnostics and test evidence contain statuses, reason codes, IDs, revisions
and counts only. Candidate text, secret values, raw transcripts and full
filesystem paths are not emitted by the new truth results.

## B1 and provenance boundary

Worker payloads without additive metadata use the compatibility source label
`worker` when an operation identity is present; direct calls without that
identity use `user`. Explicit `source` values are bounded to `user`, `worker`,
`review` and `extraction-v2`. Explicit `is_approved=False` returns
`REVIEW_REQUIRED / UNAPPROVED_CANDIDATE`; an uncommitted worker-shaped payload
remains `REVIEW_REQUIRED / UNCOMMITTED_CANDIDATE`. The existing ReviewStore
accept path and `approved=True` worker call remain unchanged. A direct
`COMMITTED` API/CLI call remains the documented trusted privileged boundary and
is not represented as proof of a ReviewStore transition.

## Deferred P2

`NEW` caller-supplied memory-ID collision remains deferred as specified by the
contract. Owner: `canonical-memory/truth maintainer`. Next package:
`W-24A-MEMORY-ID-UNIQUENESS-CONTRACT`. This report makes no claim that the
direct truth surface now enforces global memory-ID uniqueness.

## Known limitations and open failures

- Direct API/CLI callers are trusted privileged callers; this package does not
  authenticate their process or add an approval token.
- The substantive contract and implementation have not yet received the
  required independent implementation review.
- Phase 20 remains `FROZEN / LOCKED`; V2 remains `SHADOW`.
- No new P0 was observed. The deferred memory-ID collision is an open P2 by
  design.

## Independent review

Implementation review: **PENDING**. A separate read-only reviewer must inspect
the exact implementation head, source/approval derivation, registry authority,
no-write behavior, request-hash compatibility, worker/B1 boundary, focused
evidence and changed-file scope. This package does not self-SHIP.

**VERDICT:** `REVIEW PENDING`

