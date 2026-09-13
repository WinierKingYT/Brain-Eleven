# W-06C0 Contract Independent Review

**Contract reviewed:** `WEAKNESS-W06C0-RETRIEVAL-FEASIBILITY-CONTRACT.md`
**Revision reviewed:** `4e6d912540a418218126c3f0ed29637c4941708e`
**Review type:** read-only contract re-review
**Production changes:** none
**Predecessor evidence:** W-06B independent `RETHINK` at `a26912c`; W-09A evaluation boundary independently `SHIP` at `31a436c` / review commit `c6dc3bb`.

## What is sound

The contract correctly responds to W-06B's evidence without weakening the
quality floor. It keeps Phase 20 locked and V2 shadow-only, makes the package
evaluation-only, forbids changes to active retrieval and canonical authorities,
requires a machine-checkable production allowlist, and preserves W-09A's
content-free reporting, fingerprints, safety gates and DEV/TEST/HOLDOUT
discipline. The provider matrix also correctly treats unavailable embedding or
reranker providers as `NOT MEASURED`, never as a synthetic pass.

The proposed harness boundary is compatible with W-09A: identical generated
vault/task/candidate inputs, no gold labels or expected IDs passed to providers,
separate provider identity/status/error fields, and zero leakage gates across
both scored and excluded cases.

## Findings

### F1 — corpus-v3 location, manifest and case-count contract is incomplete (P1, FIX-FIRST)

Sections 2.1 and 3 require a new `corpus-v3`, but do not define its exact
repository path, manifest schema/version, directory layout, expected DEV/TEST/
HOLDOUT counts, or how its source/corpus fingerprints are constructed. W-09A
has these as explicit invariants (`evals/corpus-v2/`, manifest schema/version,
exact split directories and counts). Without the same precision, a harness can
produce a plausible but incomparable v3 while still satisfying the prose.

Amend the contract to freeze the exact `evals/corpus-v3/` path, manifest
schema/version, split file layout, counts, normalized fingerprint algorithm,
and report hash fields before implementation.

### F2 — “remove or mark NO” conflicts with the retention rule and split identity (P1, FIX-FIRST)

Section 2.1 item 3 permits removing unanswerable cases, while §3.1 says `NO`
and `REVIEW_REQUIRED` cases are retained for audit visibility. Removal changes
split counts and fingerprints; retention changes only scoring. The two rules
cannot both be the default and leave reproducibility unambiguous.

Choose one explicit rule: retain every reviewed case in its original split,
mark `NO`/`REVIEW_REQUIRED`, exclude it from quality aggregates, and report the
excluded counts. If a case must be removed for a schema/privacy reason, require
a new split manifest/version and a recorded removal reason. Do not allow an
implementer to choose between deletion and exclusion per case.

### F3 — answerability review authority and reason vocabulary are not frozen (P1, FIX-FIRST)

The follow-up amendment at `872811d` correctly aligns the status vocabulary in
§2.1 with existing IG01-C (`answerable`, `unanswerable`,
`review_required`). Section 3.1 still says reasons use a finite, versioned
vocabulary but provides only one example and no enum. It also says cases are “reviewed” without defining
the label authority, reviewer independence, tie/abstention rule, or whether
the review may inspect HOLDOUT. Since answerability determines which cases
enter quality aggregates, this is a direct anti-gaming boundary.

Freeze the reason enum and its semantics, require two-person or independent
review for public labels (with `review_required` on disagreement), record a
label/review version and provenance hash, and define the holdout-label workflow
so public tuning cannot use holdout content or labels.

The amendment also leaves a schema contradiction: §2.1/§3.1 use the lowercase
IG01-C statuses, but the JSON example in §3.1 still contains
`"status": "YES"`, and §2.1 item 3 still says `NO` cases. The contract must
use one vocabulary everywhere, including examples, exclusion counts and test
fixtures.

### F4 — variable-K metrics and provider output normalization are underspecified (P1, FIX-FIRST)

Section 5 requests “variable-K precision” but does not freeze the allowed K
set, first-K/truncation rule, duplicate handling, empty-selection convention,
or aggregate formula. W-09A freezes these details for fixed K. The provider
matrix also lacks a single normalized status/error schema for `v1`, `w06b`,
`v2`, `authority_lexical`, `embedding`, and `reranker`; “existing error
contract” and “existing fallback result” leave room for inconsistent treatment
of fallback as provider output.

Define variable K explicitly (for example `K={1,3,5,10}`), reuse W-09A's
ordered-ID and duplicate rules, and require every provider adapter to return
the existing `NormalizedEvaluationResult` plus bounded availability/status and
error fields. A fallback must identify its actual provider and be counted as a
fallback, never silently attributed to the requested provider.

### F5 — provider/source allowlist and no-artifact proof need an exact gate (P2, FIX-FIRST)

Section 6 requires a machine-checkable allowlist and forbids artifacts outside
the isolated temporary directory, but does not enumerate the allowed files or
specify the check's failure behavior. W-09A's source allowlist is itself a
versioned evidence boundary; adding corpus-v3/provider adapters without a
versioned allowlist can make source fingerprints incomparable.

Freeze the evaluation-only allowlist and explicit forbidden production paths,
require the check to fail before reports are accepted, and require a before/
after production tree or exact diff assertion proving runtime, canonical,
capture and retrieval files have zero diff.

### F6 — exit gate does not explicitly reconcile all selected provider slots (P2, FIX-FIRST)

Section 4 defines six provider slots, but §7.3's parity gate names only V1,
W-06B and V2. The contract should state whether `authority_lexical`, embedding
and reranker are mandatory when configured, or optional rows that must still
appear as `NOT MEASURED` when unavailable. Otherwise a run can omit a selected
slot while still appearing to satisfy the feasibility matrix.

### F7 — IG01-C vocabulary alignment needs an explicit W-09A adapter rule (P1, FIX-FIRST)

The `872811d` amendment correctly chooses the existing IG01-C vocabulary
`answerable` / `unanswerable` / `review_required`, but the W-09A provider
evaluator currently has a separate legacy check for `status == "NO"` and its
`corpus-v2` tasks do not carry the new lowercase field. W-06C0 must not rely on
implicit string compatibility or silently reuse W-09A's old exclusion logic.

Freeze an explicit v3-to-normalized-evaluator mapping and test that
`unanswerable` and `review_required` are excluded from quality aggregates while
their safety checks still run. Existing W-09A v2 behavior and reports must
remain byte-stable. The mapping should be evaluation-only and must reject
unknown status literals rather than treating them as answerable.

## Required amendments before implementation

1. Freeze corpus-v3 path, manifest/schema, split layout/counts and fingerprint
   construction.
2. Resolve remove-versus-retain semantics; default to retaining excluded cases
   with explicit counts.
3. Freeze answerability reason enum, independent review/disagreement rule and
   holdout labeling/timing.
4. Define one v3-to-W-09A/normalized answerability mapping, variable-K
   normalization and one provider status/fallback schema.
5. Version the evaluation allowlist and require a machine-checked zero-runtime-
   diff proof.
6. Reconcile the six provider slots with the parity/feasibility exit gates.

## Verdict

**FIX-FIRST**

The contract has the right safety boundary and is a good successor direction
after W-06B's `RETHINK`, but the corpus versioning, answerability authority,
metric normalization and provider-matrix rules are not yet precise enough to
authorize implementation without risking a new, non-reproducible benchmark.
No production implementation, retrieval tuning, V2 promotion or Phase 20 work
is authorized until these amendments receive independent review.

## Re-review at `4e6d912`

The amended contract was re-read at the exact requested revision. The previous
findings are resolved as follows:

| Finding | Verification | Result |
|---|---|---|
| F1 — corpus location/manifest/fingerprints | `evals/corpus-v3/`, fixed `dev`/`test`/`holdout` layout and counts, manifest schema/version, normalized file hashes and length-prefixed split fingerprint are frozen in §3.2. | RESOLVED |
| F2 — retain versus remove | §2.1 retains every reviewed case in its original split; exclusion is by answerability status, while removal requires a later corpus version and manifest reason. | RESOLVED |
| F3 — review authority/reasons/holdout | §3.1 freezes the six-value reason enum, two independent labelers, disagreement to `review_required`, review metadata, and sealed pre-tuning HOLDOUT labels. | RESOLVED |
| F4 — K/provider normalization | §4 freezes the six provider slots and normalized availability/run-status/fallback behavior; §5 freezes `K={1,3,5,10}`, ordered truncation, empty selection and duplicate evidence-failure behavior. | RESOLVED |
| F5 — allowlist/zero diff | §6.1 provides an exact tracked-path allowlist, explicit forbidden paths, fail-before-report behavior and before/after tree proof. | RESOLVED |
| F6 — provider parity | §7 requires all six slots in DEV/TEST feasibility rows, with explicit `NOT_MEASURED` rows for unavailable optional providers. | RESOLVED |
| F7 — v3/W09A status mapping | §4.1 scores only `answerable`, excludes `unanswerable`/`review_required` while still running safety checks, rejects unknown literals, and preserves corpus-v2/W09A behavior byte-for-byte. | RESOLVED |

The final wording correction in `4e6d912` removes the only remaining metric
ambiguity: duplicate provider IDs are rejected as evidence failures and are not
silently deduplicated. The exact status vocabulary is consistent throughout
the contract; the legacy `status == "NO"` mention is explicitly scoped to the
unchanged W-09A corpus-v2 adapter.

The exact commit diff contains only the contract document; no production,
retrieval, evaluator implementation, corpus-v2, or Phase 20 files changed in
this re-review. The contract continues to require content-free reports,
provider isolation, hard-zero safety gates, sealed HOLDOUT handling, and an
independent review before any successor runtime package is considered.

## Final verdict

**SHIP**

The W-06C0 feasibility contract is now sufficiently bounded and reproducible
to authorize the evaluation-only implementation package. This verdict does
not promote a provider, change active retrieval, open Phase 20, or authorize
W-06C1; those remain behind the contract's evidence and independent-review
gates. Unavailable providers must remain `NOT MEASURED`, and any quality
failure must remain visible.
