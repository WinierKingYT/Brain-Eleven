# W-24 Memory Truth Safety — Independent Contract Re-review 02

**Reviewed contract head:** `fb81e6e4d102dbca55ed16d120ebdf40f32ca9dd`
**Contract file revision declared inside document:** `66abdf6ba3d776b53602aace7fd21e2645d60ecc`
**Review type:** independent, read-only contract re-review
**Implementation status:** not authorized

## Previous findings

The revision explicitly closes the earlier gaps:

- legacy request projection and pre-upgrade receipt replay are specified;
- the direct API/CLI is explicitly a trusted privileged boundary, so the B1-only claim is scoped to worker-generated proposals;
- `content` and lifecycle `note` safety checks are defined and tested;
- registry corruption/read failures have a stable `SCOPE_ERROR / PROJECT_REGISTRY_UNAVAILABLE` mapping;
- global project metadata behavior is deterministic;
- the NEW caller-supplied memory-ID collision is recorded as an explicit deferred P2.

## Remaining findings

### P1 — Legacy worker effect verification conflicts with the permitted `TruthCandidate` change

The contract says implementation may add `source` and `is_approved` to `TruthCandidate`, and requires the legacy request projection for the truth engine at lines `169-190` and `324-340`. However, the unchanged worker verifier computes its expected hash with `asdict(TruthCandidate.from_mapping(values))` at `brain_eleven/runtime/worker.py:512-514`, then compares it to the stored receipt at `:516-519`. `dataclasses.asdict()` includes any newly added dataclass fields, so adding those fields makes the worker verifier’s hash differ from the required legacy projection. The contract also forbids changing the worker and says its verifier must continue observing the legacy hash at lines `149-151`, `320-323`.

Resolve this before implementation. Either require provenance to be normalized outside the dataclass fields so the worker’s existing `asdict()` shape remains unchanged, or explicitly authorize and specify the minimal worker verifier change. The current “may add fields” plus “worker unchanged” combination is not implementable as written. Add an exact worker verifier parity test at the contract level.

### P2 — Contract revision field still points to the prior commit

The actual reviewed contract head is `fb81e6e...`, but the document and report template still declare `66abdf6...` as `Contract revision` (lines `9` and `416`). `66abdf6` is the preceding revision. Since exact revision binding is a verification gate, update the field to `fb81e6e...` and retain `66abdf6` only as the previous revision if desired.

## Verdict

**FIX-FIRST**

The previous P1 findings are now addressed, but the worker request-hash contradiction must be resolved and made testable before implementation authorization. Phase 20 remains `FROZEN / LOCKED`; V2 remains `SHADOW`.
