# W-24 Direct Memory Truth Safety and Provenance Contract

**Status:** CONTRACT REVIEW PENDING — implementation is not authorized by this document
**Finding:** the direct structured-memory truth boundary uses a weaker secret
check than the shared capture policy, accepts any non-empty project ID without
checking `ProjectRegistry`, and writes fixed `source`/`is_approved` values
instead of caller-derived provenance.
**Priority:** P1 canonical-memory safety and scope authority
**Contract revision:** `09dbb76fca00004c4e7c2ef68690bf8a650fe71c` (audit baseline)

## Boundary and evidence

This package is limited to the direct `MemoryTruthEngine` path in
`scripts/memory_truth.py` and its identity-preserving adapter at
`brain_eleven/memory/truth.py`, plus focused tests.  It closes three observed
gaps without moving canonical authority.

1. `scripts/memory_truth.py:22-23` imports `MemoryStore` and scope helpers but
   does not import `capture_safety` or `ProjectRegistry`.
2. `scripts/memory_truth.py:61-64` defines `_SECRET` as one assignment-shaped
   regular expression.  `scripts/memory_truth.py:213-222` calls that expression
   from `_validate_candidate`; it does not call the shared policy and only
   checks that a project-scoped ID is non-empty.
3. `scripts/memory_truth.py:270-301` sets `source` to the literal
   `extraction-v2` at line 281 and `is_approved` to the literal `True` at line
   288.  Candidate provenance cannot affect either persisted field.
4. `scripts/memory_truth.py:303-432` owns the dry-run/commit decision flow and
   delegates committed effects to `MemoryStore.transact()`.  The direct path
   has no registry lookup, so a project ID is treated as an authority merely
   because it is present.
5. `brain_eleven/memory/truth.py:1-24` is a loader/re-export adapter.  Its
   `MemoryTruthEngine`, `TruthCandidate`, `TruthAction` and `TruthStatus` must
   remain the same objects as the legacy surface.

The shared safety authority is already present.  `scripts/capture_safety.py`
declares `capture_safety_v1` and its length/line/transcript limits at lines
9-12, covers private keys, bearer/API tokens, named secrets, passwords,
authorization values, session cookies and credential-bearing connection URLs
at lines 39-80, and exposes `evaluate_capture()`/`require_safe_capture()` at
lines 83-132.  `tests/test_capture_safety.py:30-49` exercises eight secret
classes and `:81-146` proves safety rejection precedes registry, validator and
canonical effects.

The registry authority is also already present.  `scripts/project_registry.py`
defines the `active`/`archived` lifecycle at lines 27-31, validates records at
lines 143-168, reads an identity with `get()` at lines 218-233, and exposes
fail-closed `unregistered`, `archived` and `disabled` proactive policy reasons
at lines 235-252.  The direct truth path does not use these checks today.

Read-only baseline probes at this revision showed:

| Input family | Direct truth result | Shared `capture_safety` result |
|---|---|---|
| private-key block | `NEW / NO_SCOPED_MATCH` | rejected / `potential_secret` |
| bearer token | `NEW / NO_SCOPED_MATCH` | rejected / `potential_secret` |
| API-key prefix | `NEW / NO_SCOPED_MATCH` | rejected / `potential_secret` |
| Basic authorization value | `NEW / NO_SCOPED_MATCH` | rejected / `potential_secret` |
| session cookie | `NEW / NO_SCOPED_MATCH` | rejected / `potential_secret` |
| credential-bearing connection URL | `NEW / NO_SCOPED_MATCH` | rejected / `potential_secret` |
| password assignment | `REJECT / SECRET_CONTENT` | rejected / `potential_secret` |
| named client secret assignment | `REJECT / SECRET_CONTENT` | rejected / `potential_secret` |

The same probe committed one project candidate with an unregistered ID and
`commit_new=True`: the result was `SUCCESS`, action `NEW`, revision `1`, and
one canonical memory while the registry file was absent.  The probe used
temporary vaults and emitted labels, statuses, reason codes and counts only;
it did not print secret values or alter the repository.

## Bounded objective

Make every direct truth decision use the shared capture policy, a registered
active project authority, and non-hardcoded provenance before a new canonical
effect is possible.  Keep the existing typed truth actions, lifecycle checks,
deduplication, explicit target requirement, dry-run behavior, operation
receipts and canonical transaction boundary.

The implementation may add small private helpers or additive candidate fields
inside `scripts/memory_truth.py`.  `brain_eleven/memory/truth.py` may change
only if required to re-export the same identities.  No production file outside
this direct truth surface is authorized by this contract.

### Required target behavior

1. **One safety policy.** Before truth evaluation or any registry/store effect,
   evaluate candidate content with the existing shared
   `capture_safety.evaluate_capture()` object.  Do not copy or tune its regular
   expressions.  Apply it in dry-run and commit paths, and to lifecycle text
   as well as `NEW` content.  The existing `SECRET_CONTENT` reason remains the
   compatibility mapping for `potential_secret`; other shared-policy failures
   use deterministic bounded reason codes (`CAPTURE_TOO_LARGE`,
   `CAPTURE_TOO_MANY_LINES`, `CAPTURE_TRANSCRIPT_LIKE`, or
   `CAPTURE_SAFETY_REJECTED` for an unknown policy reason).
2. **Project authority.** For `scope == project`, resolve the supplied opaque
   ID with the existing `ProjectRegistry.get()` read path.  A missing record
   returns `REJECT / PROJECT_UNREGISTERED`; an archived record returns
   `REJECT / PROJECT_ARCHIVED`; an active record with
   `proactive_capture == False` returns `REJECT / PROJECT_CAPTURE_DISABLED`.
   The registry is never auto-registered, repaired or mutated by truth
   evaluation.  An active, enabled record is the only project candidate that
   may continue.  Global candidates retain their current global behavior and
   do not require a registry lookup.
3. **Registry-owned identity.** For an accepted project candidate, the
   persisted `project_id` must be the exact registry ID.  The registry's
   project label is the authority for `project`/`project_label`; a caller label
   is display input only and cannot select, rename or widen the namespace.  No
   filesystem root is persisted or inferred in this package.  A registry read
   or registry corruption failure maps to a stable content-free scope failure
   and cannot fall back to the candidate's claim.
4. **Explicit, bounded provenance.** The candidate mapping may carry additive
   `source` and `is_approved` values.  `source` is a bounded provenance label
   from `user`, `worker`, `review` or the legacy `extraction-v2` value; an
   explicit invalid or blank value is rejected before evaluation.  The source
   is metadata, not a permission to bypass scope, safety, lifecycle or CAS.
   `is_approved`, when present, must be boolean.  `False` produces
   `REVIEW_REQUIRED / UNAPPROVED_CANDIDATE`; `True` still requires the existing
   `commitment == COMMITTED` gate.  A missing value is a compatibility input
   and derives approval from that typed commitment gate; no value may elevate
   an uncommitted candidate.
5. **Compatibility provenance fallback.** Existing worker payloads currently
   omit both additive fields.  They remain valid: a call carrying the existing
   worker operation identity receives the bounded `worker` source label, and a
   direct/CLI call without that identity receives `user`.  This fallback is
   content-free metadata and is not an authentication mechanism.  An explicit
   source always wins after validation, and `_new_record()` must map the
   normalized value rather than contain a fixed source literal.  The persisted
   `is_approved` value is the normalized result of the commitment/approval
   check, rather than an unconditional literal.
6. **Existing truth semantics.** Exact scoped fingerprint deduplication,
   claim-key conflict, explicit confirmation, supersession and resolution
   continue to use the current `TruthAction`/`TruthStatus` values and target
   checks.  New scope/provenance rejections are decisions, not lifecycle
   mutations.  `commit_new`, `expected_revision`, `operation_id`, request-hash
   replay and the existing error mappings retain their public shapes.

## Authority, transaction and no-write invariants

- `MemoryStore` remains the sole canonical memory authority.  Every accepted
  mutation still goes through the current `MemoryStore.transact()` lock,
  reload, expected-revision CAS, revision increment, backup and atomic replace
  sequence (`scripts/memory_store.py:227-246`).  No direct JSON write or second
  memory store is permitted.
- `StateStore`, `StateBoundary`, `ProjectRegistry` implementation and all
  registry mutation/locking behavior remain unchanged.  Truth only reads the
  registry identity/status/policy; it never writes state or registers a
  project.
- A model proposal, uncertain/quoted/question content, or missing B1 approval
  cannot become canonical merely by setting `source` or `is_approved`.  The
  existing B1 review action remains the approval transition, and B2 remains
  deterministic grouping/order only.  The worker still calls the same truth
  engine with the same operation IDs and validates the same canonical effect
  (`brain_eleven/runtime/worker.py:137-163` and `:733-790`).
- On a safety, scope or provenance rejection, the rejected candidate produces
  no canonical memory, lifecycle mutation, revision increment, backup,
  operation receipt, registry mutation, state mutation, graph/retrieval
  effect, queue effect or review write.  A mixed batch may retain the existing
  per-candidate decision semantics; the rejected candidate itself must have
  zero effect, and a receipt is written only under the existing all-eligible
  receipt rule.
- Exact operation replay remains idempotent: the same operation ID and request
  hash return the existing content-free receipt/effect without a second memory.
  A changed candidate or provenance envelope under that operation ID remains a
  replay mismatch.  A stale `expected_revision` remains `STALE_INPUT` with no
  write.
- Rejected decisions and review decisions remain content-free.  Diagnostics
  may include IDs, status, reason, policy name, registry state and revisions,
  but never candidate text, secret values, raw transcript material or full
  filesystem paths.

## Compatibility and preserved surfaces

- `TruthAction`, `TruthStatus`, `TruthCandidate`, `TruthDecision`,
  `TruthResult`, CLI flags and result keys remain compatible.  New reason codes
  are additive; `SECRET_CONTENT`, `SCOPE_UNRESOLVED`, lifecycle reasons,
  `STALE_INPUT` and existing success/degraded mappings remain stable.
- Existing canonical records are not rewritten or reclassified.  The
  deterministic `source_id` shape `truth:<candidate_id>`, record schema,
  lifecycle fields, scope fields and retrieval inputs remain available.
- `brain_eleven.memory.truth` remains an adapter, not a second implementation;
  package/legacy/bare-loader object identity tests continue to pass
  (`tests/test_pre12_memory_state_caller_migration.py:250-265`).
- The worker's queue, extraction, operation receipt, B1 approval and B2
  grouping/order paths remain behaviorally unchanged.  Existing worker calls
  that omit the additive provenance fields use the compatibility fallback
  above.
- Explicit manual `brain_eleven.memory.capture.remember()` remains an explicit
  user capture path.  Its shared safety ordering and validator/store ownership
  (`brain_eleven/memory/capture.py:78-127`) are regression surfaces, not a new
  truth call or proactive-policy rewrite.
- Existing `tests/test_memory_truth.py` fixtures that use synthetic project IDs
  must register those IDs as active/enabled temporary projects, or use global
  scope, so the tests describe the new authority boundary.  No production
  fixture, registry, or historical canonical record is migrated.

## Required tests and metrics

### Baseline and focused reproduction

- Record the exact implementation SHA separately from this contract revision,
  and preserve the baseline probe table above without printing sensitive input.
- Test all eight shared-policy secret classes from
  `tests/test_capture_safety.py:30-49`: private key, bearer token, API-key
  prefix, named client secret, password assignment, Basic authorization,
  session cookie and credential-bearing connection URL.  Every class must
  return a bounded rejection and produce zero memory/receipt/revision effect.
- Include safe security discussion, ordinary user decision text and a valid
  worker commitment as accepted controls; shared-policy size, line-count and
  transcript-like failures must reject as well.

### Scope and provenance cases

- An unregistered project ID, an archived project ID and an active disabled
  project ID each reject with the documented reason, leave registry and memory
  bytes/revisions unchanged, and create no backup or receipt.
- An active, enabled registered project accepts a valid direct user candidate;
  the stored source is `user` and approval is derived from `COMMITTED`.
- The existing worker-shaped candidate and operation ID accept through the
  unchanged worker path; its stored source is the bounded worker/legacy
  compatibility value and approval remains true only after the existing
  commitment gate.  A B1 review accept continues to be the only route for a
  pending proposal.
- Missing/invalid source, non-boolean approval, explicit approval false,
  non-`COMMITTED` commitment, contradictory project label and global/project
  identity cases are covered.  None may bypass safety or registry authority.
- Package adapter identity, direct/CLI dry-run, lifecycle target checks,
  cross-project target rejection, exact-fingerprint deduplication and
  content-free results remain covered.

### Idempotence, CAS and regression metrics

- Repeating one accepted `operation_id` with the same request/provenance hash
  returns the same receipt and memory ID with no revision increase.  Reusing
  it with changed content, source or approval returns a replay mismatch with
  no write.
- A stale `expected_revision` returns the existing `STALE_INPUT`/
  `MEMORY_STORE_CONFLICT` mapping; concurrent valid writers retain the current
  lock/CAS behavior.
- Capture, memory truth, worker/B1, B2 ordering, package migration, retrieval
  filtering and manual-capture regression suites pass without weakening their
  existing assertions.  Pending/rejected B1 candidates remain absent from
  canonical retrieval, and accepted records remain discoverable under their
  existing scope.

## Verification gates

1. **Boundary proof:** read-only source/AST review shows the direct truth path
   calls the single shared safety object, reads the existing registry authority,
   contains no copied secret policy, no direct file write and no second truth
   or provenance authority.  The changed-file list is limited to this package's
   truth surface and focused tests.
2. **Safety/scope proof:** all eight secret classes and all three negative
   registry states reject with zero canonical, registry, receipt, review,
   state, graph or retrieval effects; active/enabled user and worker controls
   commit exactly once with the expected provenance.
3. **Compatibility proof:** focused truth, package identity, migration,
   capture-safety, manual capture, worker/B1 and B2 tests pass; existing
   lifecycle, dedup, retrieval and Phase 20 frozen/V2 shadow assertions remain
   unchanged.
4. **Full verification:** at one exact revision, run `pytest tests -q`,
   critical flake8 (`E9,F63,F7,F82`), Python compile/import sanity and
   `git diff --check`.  Record pass/fail counts and any pre-existing failure
   separately.
5. **Independent review:** a read-only reviewer checks the evidence, source
   and approval derivation, registry authority, no-write behavior, lock/CAS
   preservation, worker/B1 compatibility and changed-file scope, then returns
   only `SHIP`, `FIX-FIRST` or `RETHINK`.  The implementation cannot self-SHIP.

## Explicit non-goals

- No change to `MemoryStore`, `StateStore`, `ProjectRegistry`, their schemas,
  locks, CAS, backups, atomic persistence or mutation APIs.
- No worker, queue, evidence, extraction, model, B1 review, B2 ordering,
  `StateBoundary`, manual capture, graph or retrieval implementation change.
- No second safety regex, secret-pattern tuning, source authentication system,
  transcript provenance redesign or project-root/ID migration.  Root/ID
  mismatch work remains W-13 scope.
- No rewrite, repair or backfill of historical records with the old source or
  approval values; no canonical schema migration is introduced for additive
  provenance inputs.
- No change to lifecycle policy, dedup ranking, claim conflict rules, API
  response design, CLI flags, V2 promotion/default rollout or Phase 20.
- No automatic project registration, archive reactivation, proactive opt-in
  change, review bypass, state mutation or model-to-memory authority grant.

## Package report template

```text
PACKAGE: W-24
CONTRACT REVISION: 09dbb76fca00004c4e7c2ef68690bf8a650fe71c
IMPLEMENTATION REVISION: <exact SHA, only after authorization>
OBJECTIVE: Apply shared capture safety, registered project authority and
           derived provenance to the direct MemoryTruthEngine commit path.
FILES CHANGED: ...
ROOT CAUSE ADDRESSED: weak _SECRET gate; no ProjectRegistry lookup; hardcoded
                      source/is_approved in _new_record.
BASELINE EVIDENCE: 8 secret classes (<baseline rejected>/<8> direct truth
                    rejection); unregistered commit accepted; fixed source /
                    approval observed at scripts/memory_truth.py:270-301.
TESTS ADDED: ...
TESTS EXECUTED: ...
QUALITY METRICS BEFORE: secret bypass count, unregistered effect count,
                        hardcoded provenance count
QUALITY METRICS AFTER: 0 secret bypasses, 0 unregistered/archived/disabled
                       effects, normalized user/worker provenance
SAFETY METRICS: zero rejected-candidate writes; zero sensitive output; zero
                registry/state/review/receipt side effects on rejection
SCOPE METRICS: active/enabled acceptance; negative registry reason counts;
               cross-project and global controls
IDEMPOTENCE/CAS: replay/effect IDs, revision deltas, mismatch and stale counts
KNOWN LIMITATIONS: ...
OPEN FAILURES: ...
INDEPENDENT REVIEW: SHIP / FIX-FIRST / RETHINK
VERDICT: CONTRACT REVIEW PENDING
PHASE20: FROZEN / LOCKED
V2: SHADOW
```

**Implementation authorization:** not granted until independent contract
review.  This document records a bounded review target only; it is not
approval to implement or self-SHIP.
