# W-24 Memory Truth Safety — Independent Contract Re-review 04

**Reviewed metadata head:** `1ef38125ecbe3586b83f564dfc0607765b59d5a9`
**Substantive contract revision:** `091e064b0a4e95b6f6fbe4c1cc97932d0d7900f0`
**Review type:** independent, read-only contract re-review
**Implementation status:** not authorized by this review alone

## Verification

The previous pending-B1 ambiguity is resolved. The contract now separates the
boundaries precisely:

- In the worker boundary, an input with no commitment is normalized by the
  unchanged `_memory_candidate_values(..., approved=False)` path to
  `UNCERTAIN`, which the truth engine must return as
  `REVIEW_REQUIRED / UNCOMMITTED_CANDIDATE`.
- Only the existing `ReviewStore` accept path calls
  `apply_candidate(..., approved=True)` and turns that worker input into
  `COMMITTED` for canonical application.
- A generic direct `process(COMMITTED)` mapping is explicitly a trusted
  privileged call. The contract makes no false claim that it carries B1 proof;
  its direct acceptance is tested separately.

This is consistent with the unchanged current code at
`brain_eleven/runtime/worker.py:67-77`, `:743-750`, and
`brain_eleven/runtime/service.py:46-63`, and with the B1 fixture shape in
`tests/test_ig04_b1_human_approval.py:52-64`.

The earlier worker request-hash finding is also closed: `TruthCandidate` and
`dataclasses.asdict()` remain pre-W-24 shape, the legacy request projection is
the only `request_hash`, and provenance is a mapping sidecar plus additive
receipt field. The unchanged verifier at
`brain_eleven/runtime/worker.py:512-519` is explicitly covered by parity tests.

The contract now also contains executable requirements for shared content and
lifecycle-note safety, registry authority and unavailable-registry mapping,
global metadata rejection, pre-upgrade receipt replay, direct/worker
provenance, and the deferred NEW memory-ID collision P2. Its implementation
boundary remains limited to the direct truth surface and adapter/focused tests;
Phase 20/V2 status and implementation authorization remain correctly closed.

## Non-blocking metadata note

The document intentionally distinguishes the substantive contract revision
`091e064...` from the final metadata head `1ef3812...`. Evidence and the later
package report should record both values exactly, as this review does.

## Verdict

**SHIP**

The W-24 contract is bounded, internally consistent, and implementable. This
verdict authorizes no implementation by itself; implementation still requires
the project’s separate human authorization and must end with an independent
implementation review. Phase 20 remains `FROZEN / LOCKED`; V2 remains
`SHADOW`.
