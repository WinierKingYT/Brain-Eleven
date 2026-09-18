# W-24 Memory Truth Safety — Independent Contract Re-review 03

**Reviewed metadata head:** `0ad5fe5d118c03df1d8b0e0a258e2dadf13f5b8b`
**Substantive contract revision:** `c4b6277c073cfd0a396725434e53427b5af73e0d`
**Review type:** independent, read-only contract re-review
**Implementation status:** not authorized

## Closed findings

The sidecar revision resolves the prior worker-hash blocker. It explicitly freezes the pre-W-24 `TruthCandidate` dataclass and `dataclasses.asdict()` shape, keeps the legacy request projection as the only `request_hash`, and puts provenance in a receipt-only sidecar. The unchanged worker verifier at `brain_eleven/runtime/worker.py:512-519` can therefore continue to compute the same hash. The earlier safety, lifecycle-note, registry-error, global-metadata, receipt-replay, B1 direct-privileged-boundary, and duplicate-ID-deferral findings are also explicitly addressed.

## Remaining finding

### P1 — Pending B1 candidates are not distinguishable from approved worker candidates

The contract correctly documents the direct API/CLI as a trusted privileged boundary and removes the impossible claim that B1 is the only route for direct calls (contract lines `125-133`, `462-464`). However, it still requires at lines `361-366` that a pending worker proposal remain pending until the B1 review action and asks for a test proving that direct truth processing does not implicitly approve that proposal.

The unchanged runtime has a real ambiguous case: when `b1_human_approval=True`, `brain_eleven/runtime/worker.py:743-750` routes every candidate to review, including a user candidate whose commitment is `COMMITTED`; `tests/test_ig04_b1_human_approval.py:52-64` uses exactly that shape. The same candidate mapping has no approval sidecar before review. `apply_candidate()` then builds the truth payload at `brain_eleven/runtime/worker.py:67-77`, and the contract’s compatibility rule derives approval from `COMMITTED` when the field is absent. A direct `MemoryTruthEngine.process()` call with that pending mapping is therefore indistinguishable from an approved worker call and would be accepted. The authorized W-24 files do not read `ReviewStore`, carry a review token, or receive an approval marker from the unchanged worker/service path.

Resolve the contract by choosing one testable rule: either limit the “pending proposal” assertion to proposals with non-committed commitment (for example model `PROPOSED`) and explicitly accept that a committed pending mapping is inside the trusted direct boundary, or authorize a concrete approval signal/integration outside this package. The current requirement cannot be satisfied while keeping both the worker byte-unchanged boundary and the missing-provenance `COMMITTED` fallback.

## Metadata note

The document identifies `c4b6277...` as the substantive contract revision while the reviewed file head is `0ad5fe5...`, which only records that revision in metadata. This is understandable, but the implementation package report should bind evidence to the full reviewed metadata head and retain the substantive revision as its parent/content revision.

## Verdict

**FIX-FIRST**

The worker hash design is now implementable, but the pending-B1 acceptance criterion needs one final scope/behavior clarification before implementation authorization. Phase 20 remains `FROZEN / LOCKED`; V2 remains `SHADOW`.
