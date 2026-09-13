# W-06C0R1 Contract Independent Review

**Contract reviewed:** `WEAKNESS-W06C0R1-ANSWERABILITY-PROVENANCE-CONTRACT.md`
**Revision reviewed:** `946b5cd0fddf8727215d25d0aa4babd817632886`
**Review type:** independent read-only contract re-review
**Production changes:** none
**Predecessor:** W-06C0 implementation independently `FIX-FIRST` at `60f8e08`

## What is sound

The contract keeps Phase 20 locked and V2 shadow-only, freezes corpus-v3 and
predecessor reports, bounds implementation paths, and excludes production,
canonical stores, active retrieval, provider promotion and private data. The
corpus-v4 minimum counts and per-split phenomenon requirements directly address
the zero-answerable TEST/HOLDOUT failure. The two-labeler model, disagreement
handling, case/attestation binding, manifest and split fingerprints, explicit
version selection, provider snapshot parity, privacy rules and fail-closed exit
gates are all appropriate foundations.

## Findings

### F1 — candidate and task-set fingerprint formulas are still incomplete (P1, FIX-FIRST)

Section 5 names `candidate_content_fingerprint` as sorted
`(candidate_id, normalized_content)` frames and `candidate_order_fingerprint` as
ordered candidate IDs, but it does not freeze the exact hash operation and
framing for either value. It also requires a task-set fingerprint without
defining its canonical input, ordering, length-prefix framing, or `sha256:`
encoding. The contract's Section 4 formula is precise for hashes generally,
but it does not remove the ambiguity about whether these snapshot fingerprints
are JSON objects, concatenated frames, or another representation. Since
provider parity is a hard gate, two correct implementations could compute
different values or omit split/revision binding.

Freeze explicit formulas for all three values. State the exact normalized
tuple/object, sort key, path or field framing, source revision/split binding,
digest encoding and required `sha256:<64 lowercase hex>` form. Add a test that
reorders candidates, changes content, changes revision, and changes ordered case
IDs and proves the corresponding fingerprint changes.

### F2 — “no case IDs to providers” conflicts with the existing provider contract (P1, FIX-FIRST)

Section 5 forbids passing case IDs to provider code, while the existing
`GoldenTask`/`NormalizedEvaluationResult` provider boundary carries `task_id`
and the current provider adapters use `task.task_id`. The contract also
requires a task-set fingerprint over ordered case IDs. Without an explicit
opaque runtime-handle mapping, an implementation must either violate the
privacy/anti-label rule, change existing provider interfaces outside the
allowlist, or silently pass a corpus case identifier through the task object.

Define whether providers receive an opaque per-run task handle and how the
harness maps it back to the public case ID after provider execution, or state
that the existing `task_id` field is allowed only as a non-semantic opaque
handle and is excluded from provider inputs used for tuning. The rule must be
testable at the provider boundary and must preserve W-09A/IG01-C behavior.

### F3 — HOLDOUT sealing lacks a machine-checkable chronology/seal artifact (P2, FIX-FIRST)

The contract requires HOLDOUT labels and attestations to be created before
tuning and sealed before the final probe, and it requires final-probe command
evidence. It does not define the seal marker or the evidence that proves the
DEV/TEST implementation and reports were frozen before the HOLDOUT labels were
opened. A later implementation could satisfy the final command shape while
having read or tuned against HOLDOUT earlier.

Require a content-free seal record containing the corpus/manifest/attestation
fingerprints, the DEV/TEST evidence revision or report hashes, and an explicit
unlock transition consumed only by the final-probe command. DEV/TEST runs must
fail when the seal is absent or already unlocked; the final probe must record
the seal hash and unlock event.

### F4 — predecessor status is factually stale (P2, documentation)

The header identifies W-06C0 as `FIX-FIRST` at `4e6d912`, which was the
contract review that shipped. The actual W-06C0 implementation/evidence review
was `FIX-FIRST` at `60f8e08`, while the amended contract was reviewed `SHIP` at
`fa5b920`. This does not weaken the technical gates, but it makes the audit
chain ambiguous. Bind the predecessor field to the exact intended artifact and
verdict before implementation starts.

## Verification summary

- Corpus-v3 immutability is explicitly preserved.
- Corpus-v4 counts and minimum answerable thresholds are concrete and cannot
  be met by silently relabeling unanswerable cases.
- Case payload and attestation hashes bind the case, decisions and agreement;
  raw labeler identities are excluded.
- Manifest and split hashing, exact allowlist/forbidden paths, privacy rules,
  optional-provider handling, and safety/provider parity are directionally
  sound.
- No production or evaluator implementation was changed in this review.

## Verdict

**FIX-FIRST**

The contract is a strong correction to W-06C0, but the snapshot/task identity
rules and HOLDOUT chronology must be made machine-exact before implementation.
No W-06C0R1 implementation, provider tuning, W-06C1 runtime work, V2
promotion, or Phase 20 work is authorized by this review.

## Re-review at `946b5cd`

The amended contract was re-read at the exact requested revision. The previous
findings are resolved:

| Finding | Verification | Result |
|---|---|---|
| F1 — snapshot/task fingerprint ambiguity | §4.4 now fixes row fields, candidate sort key, u64 framing, source-revision binding, ordered IDs, split binding, digest format and mutation tests. | RESOLVED |
| F2 — provider case-ID boundary | §5 defines an opaque per-run `task_handle`, uses it only through the existing task-id field, keeps the public case-ID mapping outside provider input, and forbids label inference. | RESOLVED |
| F3 — HOLDOUT chronology/seal | §6 defines the sealed record, bound DEV/TEST revision and report hashes, explicit final-probe unlock, evidence hashes and one-time replay failure. | RESOLVED |
| F4 — predecessor audit reference | The header now distinguishes W-06C0 contract `SHIP` at `fa5b920` from implementation/evidence `FIX-FIRST` at `60f8e08`. | RESOLVED |

The exact amendment diff is documentation-only. Corpus-v3 immutability,
corpus-v4 minimum answerable counts, two-labeler attestation, privacy and
allowlist boundaries, provider parity, split/version discipline and the
independent exit gate remain intact. No new blocker was found in this
re-review.

## Final verdict at `946b5cd`

**SHIP**

The W-06C0R1 contract is sufficiently precise to authorize its bounded,
evaluation-only implementation. This verdict does not authorize W-06C1,
provider promotion, retrieval changes, V2 promotion or Phase 20 work; each
remains behind the contract's evidence and independent-review gates.
