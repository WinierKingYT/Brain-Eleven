# W-24 Memory Truth Safety — Independent Contract Review

**Reviewed contract:** `WEAKNESS-W24-MEMORY-TRUTH-SAFETY-CONTRACT.md`
**Contract file revision:** `4e95487237e328fb19104c143f356239e6d8f6a9`
**Review type:** independent, read-only contract review
**Implementation status:** not authorized

## Findings

### P1 — Existing operation receipts can lose replay compatibility

The contract permits adding `source` and `is_approved` to `TruthCandidate`, while the current request identity is computed from `asdict(candidate)` at `scripts/memory_truth.py:322-324`; existing receipts are compared byte-for-byte at `:338-342`. Adding dataclass fields changes the request hash even when old callers omit both fields. A receipt created before the change could therefore return `Operation identity mismatch` instead of replaying safely. The contract promises existing operation IDs and replay behavior at lines `159-163` and `182-184`, but does not define a legacy hash projection or require a pre-upgrade receipt replay test. Add an explicit compatibility rule and fixture: an old receipt with omitted provenance fields must replay with no second effect; changed provenance must still be a mismatch.

### P1 — The B1 “only review route” guarantee is not enforceable inside this scope

The contract says `source` is metadata and not permission at lines `109-118`, while the direct CLI still exposes `--commit-new` at `scripts/memory_truth.py:443-455` and `MemoryTruthEngine.process()` accepts any `COMMITTED` candidate. No review receipt, ReviewStore token, or trusted caller proof is available in the authorized files. Consequently, a caller can submit a committed candidate with `is_approved=True` (or omit it) without passing the B1 review action, contradicting lines `146-148`, `217-219`, and the “no review bypass” non-goal. Either narrow the claim to the existing trusted worker/review integration and document the direct API as privileged, or authorize a concrete approval proof. Do not leave “B1 is the only route” as an untestable acceptance claim.

### P1 — Lifecycle notes are a remaining canonical secret path

The safety requirement at lines `84-91` says to cover lifecycle text, but the required secret tests at lines `200-210` are described only for candidate content. Existing lifecycle mutations persist `candidate.note` into `supersession_note`/`resolution_note` at `scripts/memory_truth.py:363-375`. Checking only `content` would still allow a secret in `note` to enter canonical memory. Define the exact text fields covered (at minimum `content` and `note`) and add rejection/no-effect tests for lifecycle notes.

### P1 — Registry failure result is underspecified and not covered

The contract requires a stable content-free scope failure for registry read/corruption at lines `102-108`, but does not specify its `TruthStatus`, `error_code`, or per-candidate decision shape. `ProjectRegistryError` is a `ValueError` (`scripts/project_registry.py:34`), and the current outer catch at `scripts/memory_truth.py:439-440` maps it to the generic `MEMORY_TRUTH_FAILED`. Add an explicit mapping (for example `SCOPE_ERROR` plus a stable registry-unavailable code) and tests for malformed registry JSON/read failure, while keeping missing, archived, and disabled project reasons distinct.

### P2 — Contract revision identifier is not the contract’s commit

The file was introduced by `4e95487`, but its header and package template identify `09dbb76...`, which is the preceding TSC-02 documentation commit. Exact revision evidence is a stated gate; label `09dbb76` as the audit baseline and record `4e95487` as the contract revision.

### P2 — Duplicate-ID finding is neither closed nor explicitly deferred

The prior audit identified caller-supplied NEW `successor_memory_id` collision risk. This contract does not mention it in the target, non-goals, known limitations, or tests, although duplicate ID is a requested review concern. State explicitly that W-24 defers this P2 (with an owner/next package), or add a bounded rejection test/fix. Do not let the W-24 report imply that the direct truth surface is fully hardened.

### P2 — Global candidates carrying project metadata have no defined result

`infer_memory_scope()` treats global records as global even when project fields are present, while `_new_record()` currently persists `project`, `project_label`, and `project_id` (`scripts/memory_truth.py:295-300`). The contract mentions global/project identity cases at line `221` but does not say whether contradictory project fields are rejected or normalized away. Choose and test one deterministic behavior so global records cannot retain misleading project identity metadata.

## Verdict

**FIX-FIRST**

The contract is bounded and addresses real P1 findings, but implementation must wait until the four P1 gaps above are made explicit and testable. Phase 20 remains `FROZEN / LOCKED`; V2 remains `SHADOW`.
