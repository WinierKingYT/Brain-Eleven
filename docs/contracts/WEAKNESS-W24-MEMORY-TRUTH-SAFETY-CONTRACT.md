# W-24 Direct Memory Truth Safety and Provenance Contract

**Status:** CONTRACT REVIEW PENDING — implementation is not authorized by this document
**Finding:** the direct structured-memory truth boundary uses a weaker secret
check than the shared capture policy, accepts any non-empty project ID without
checking `ProjectRegistry`, and writes fixed `source`/`is_approved` values
instead of caller-derived provenance.
**Priority:** P1 canonical-memory safety and scope authority
**Audit baseline:** `0ad5fe5d118c03df1d8b0e0a258e2dadf13f5b8b`
**Contract revision:** `091e064b0a4e95b6f6fbe4c1cc97932d0d7900f0`

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
   288.  Candidate provenance cannot affect either persisted field.  The
   additive fields proposed below also have a replay compatibility hazard:
   `scripts/memory_truth.py:322-324` hashes `asdict(candidate)`, while
   `:338-342` compares that hash byte-for-byte against an existing operation
   receipt.  `brain_eleven/runtime/worker.py:512-519` independently computes
   the expected worker request hash from `asdict(TruthCandidate.from_mapping(values))`;
   changing that dataclass/asdict shape would invalidate the worker verifier.
   The worker boundary also has a separate approval distinction: its
   `_memory_candidate_values(candidate, approved=False)` helper defaults an
   omitted commitment to `UNCERTAIN` at `brain_eleven/runtime/worker.py:67-77`,
   while `brain_eleven/runtime/service.py:46-63` sets `COMMITTED` and passes
   `approved=True` only after a `ReviewStore` accept.  A generic
   `MemoryTruthEngine.process()` call receives only the reduced candidate
   mapping, so it cannot tell that a `COMMITTED` value came from that review
   transition.  The current B1 fixture at
   `tests/test_ig04_b1_human_approval.py:52-64` already has `COMMITTED` in its
   pending-shaped candidate while `brain_eleven/runtime/worker.py:743-750`
   routes it to review, which is the concrete ambiguity this contract records.
4. `scripts/memory_truth.py:303-432` owns the dry-run/commit decision flow and
   delegates committed effects to `MemoryStore.transact()`.  The direct path
   has no registry lookup, so a project ID is treated as an authority merely
   because it is present.
5. `scripts/memory_truth.py:364-375` writes `candidate.note` into
   `supersession_note`/`resolution_note` without passing that note through the
   secret policy; checking only `content` would leave a lifecycle-note secret
   path.
6. `scripts/memory_truth.py:295-300` persists project metadata even for a
   global candidate, and `:399-401` accepts a caller-supplied
   `successor_memory_id` for `NEW`, which can collide with an existing memory
   ID.  The latter is a separate deferred P2 below.
7. `brain_eleven/memory/truth.py:1-24` is a loader/re-export adapter.  Its
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

Read-only baseline probes at the audit baseline showed:

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

The implementation may add small private helpers and parse additive mapping
metadata inside `scripts/memory_truth.py`.  `brain_eleven/memory/truth.py` may
change only if required to re-export the same identities.  `TruthCandidate`'s
public dataclass field list, field order and `dataclasses.asdict()` output are
frozen at the pre-W-24 shape; `source` and `is_approved` must not become
dataclass fields.  They may exist only in the input mapping and an internal
normalized provenance sidecar carried alongside the unchanged candidate.  No
production file outside this direct truth surface is authorized by this
contract.

The B1 approval guarantee is deliberately narrower than the direct truth
contract.  At the existing worker/review boundary, an unapproved worker-shaped
input with no commitment is normalized by
`_memory_candidate_values(candidate, approved=False)` to `commitment=UNCERTAIN`,
and the truth decision is `REVIEW_REQUIRED / UNCOMMITTED_CANDIDATE`.  A
`ReviewStore` accept is the only B1 approval transition in that worker boundary:
the existing service calls `apply_candidate(..., approved=True)`, whose worker
helper produces `commitment=COMMITTED` before the truth apply.  The
`approved=True` call boundary is the B1 proof; it is not encoded in the public
`TruthCandidate` or inferred from its fields.  Because the unchanged helper
preserves a commitment that an input mapping already supplies when
`approved=False`, a pending mapping that already says `COMMITTED` is an
ambiguous shape; W-24 accepts that the generic engine cannot distinguish it
from a direct privileged call and does not label either call B1-approved.

### Required target behavior

1. **One safety policy and exact text inputs.** Before truth evaluation or any
   registry/store effect, evaluate `candidate.content` after the existing
   string normalization with the shared `capture_safety.evaluate_capture()`
   object.  `content` is required and is checked for every operation: it is
   the proposed memory text for `NEW` and the successor text for
   `SUPERSEDE_EXISTING`; it is still checked for `CONFIRM_EXISTING` and
   `RESOLVE_EXISTING` even when no new record is written.  `candidate.note` is
   a separate optional text field.  When non-empty, check the normalized note
   with the same policy before it can influence a lifecycle mutation; for
   `SUPERSEDE_EXISTING` it is the only value written to `supersession_note`,
   and for `RESOLVE_EXISTING` it is the only value written to
   `resolution_note`.  An empty note is normalized to empty and is not
   persisted.  A rejected content or note maps `potential_secret` to the
   compatibility reason `SECRET_CONTENT`; other shared-policy failures use
   deterministic bounded reasons (`CAPTURE_TOO_LARGE`,
   `CAPTURE_TOO_MANY_LINES`, `CAPTURE_TRANSCRIPT_LIKE`, or
   `CAPTURE_SAFETY_REJECTED` for an unknown policy reason).  Do not copy or
   tune the shared regular expressions.  Apply this policy in dry-run and
   commit paths, before registry lookup and before the MemoryStore
   transaction.
2. **Project authority.** For `scope == project`, resolve the supplied opaque
   ID with the existing `ProjectRegistry.get()` read path.  A missing record
   returns `REJECT / PROJECT_UNREGISTERED`; an archived record returns
   `REJECT / PROJECT_ARCHIVED`; an active record with
   `proactive_capture == False` returns `REJECT / PROJECT_CAPTURE_DISABLED`.
   The registry is never auto-registered, repaired or mutated by truth
   evaluation.  An active, enabled record is the only project candidate that
   may continue.  Global candidates do not require a registry lookup.
3. **Deterministic global metadata rule.** Global scope rejects any non-empty
   `project_id`, `project` or accepted `project_label` alias with
   `REJECT / GLOBAL_PROJECT_METADATA`.  It never normalizes that metadata into
   a global record and never performs a registry lookup.  Project scope may
   carry a caller label, but the label is normalized from the registry below.
4. **Registry-owned identity.** For an accepted project candidate, the
   persisted `project_id` must be the exact registry ID.  The registry's
   project label is the authority for `project`/`project_label`; a caller label
   is display input only and is replaced by the registry label when it differs.
   It cannot select, rename or widen the namespace.  No filesystem root is
   persisted or inferred in this package.  A registry read or registry
   corruption failure maps to the explicit availability result below and
   cannot fall back to the candidate's claim.
5. **Explicit, bounded provenance.** The candidate mapping may carry additive
   `source` and `is_approved` values.  `source` is a bounded provenance label
   from `user`, `worker`, `review` or the legacy `extraction-v2` value; an
   explicit invalid or blank value is rejected before evaluation.  The source
   is metadata, not a permission to bypass scope, safety, lifecycle or CAS.
   `is_approved`, when present, must be boolean.  `False` produces
   `REVIEW_REQUIRED / UNAPPROVED_CANDIDATE`; `True` still requires the existing
   `commitment == COMMITTED` gate.  A missing value is a compatibility input
   and derives approval from that typed commitment gate; no value may elevate
   an uncommitted candidate.
6. **Direct privileged path and B1 boundary.** The direct
   `MemoryTruthEngine.process()` API and `scripts/memory_truth.py` CLI
   `--commit --commit-new` are trusted privileged write surfaces in this
   package.  Their caller is responsible for supplying structured,
   `COMMITTED` input and valid provenance; W-24 does not authenticate that
   caller or add an approval token.  A generic `process(COMMITTED)` mapping
   contains no ReviewStore acceptance marker and cannot be classified as
   B1-approved.  W-24 therefore makes no claim that B1 is the only approval
   route for direct API/CLI calls, and direct success is reported as the
   trusted privileged boundary it is.

   Within the existing worker boundary when B1 is enabled, the worker routes a
   pending candidate to `ReviewStore` before applying it.  The unapproved
   worker-shaped control is the mapping with no commitment: existing
   `_memory_candidate_values(candidate, approved=False)` yields `UNCERTAIN`,
   which the truth engine returns as `REVIEW_REQUIRED /
   UNCOMMITTED_CANDIDATE`.  Only the existing `ReviewStore` accept invokes
   worker `apply_candidate(..., approved=True)`, yielding `COMMITTED` for the
   canonical apply.  This scoped transition is the B1 guarantee; it does not
   assert that an indistinguishable direct `COMMITTED` mapping carries B1
   proof.
7. **Compatibility provenance fallback.** Existing worker payloads currently
   omit both additive fields.  They remain valid: a call carrying the existing
   worker operation identity receives the bounded `worker` source label, and a
   direct/CLI call without that identity receives `user`.  This fallback is
   content-free metadata and is not an authentication mechanism.  An explicit
   source always wins after validation, and `_new_record()` must map the
   normalized value rather than contain a fixed source literal.  The persisted
   `is_approved` value is the normalized result of the commitment/approval
   check, rather than an unconditional literal.
8. **Receipt/replay compatibility.** Accepting `source` and `is_approved` in
   an input mapping must not change the `TruthCandidate` public dataclass,
   field order or `asdict()` result.  The parser may return the unchanged
   candidate plus an internal normalized provenance sidecar; a legacy
   `TruthCandidate` object passed directly to the engine follows the same
   legacy path and hash.  Define `legacy_request_projection(candidate)` as
   the exact pre-W-24 ordered field allowlist from
   `candidate_id` through `note` (the fields currently present at
   `scripts/memory_truth.py:78-94`), excluding all provenance metadata, and
   compute the only `request_hash` as
   `identity("request_", [legacy_request_projection(candidate)])`.  There is
   no v2 request hash.  Keep this projection unchanged for worker-shaped calls,
   existing receipts and the current worker verifier.  Add only an optional
   `provenance_hash` field inside newly written operation receipts, over the
   ordered normalized `(source, is_approved)` pair for each candidate, so a
   changed provenance envelope cannot replay merely because the legacy request
   hash is equal.  A pre-W-24 receipt without `provenance_hash` may replay only
   when the incoming mapping omits both additive metadata fields; supplying
   either field against that receipt returns `INVALID_INPUT /
   OPERATION_REPLAY_MISMATCH` and performs no write.  New receipts compare the
   historical request hash and `provenance_hash`.  The existing worker effect
   verifier at `brain_eleven/runtime/worker.py:512-519` must continue to see
   the historical request hash for its current worker-shaped payload; worker
   source is unchanged and no receipt replay may fail solely because the
   mapping metadata was introduced.

   The allowlist is explicit and ordered for review purposes:
   `candidate_id`, `content`, `memory_type`, `scope`, `project_id`, `project`,
   `dedup_fingerprint`, `claim_key`, `commitment`, `confidence`,
   `evidence_refs`, `occurred_at`, `operation`, `target_memory_id`,
   `successor_memory_id`, `resolved_by`, `note`.  The new provenance fields
   are never silently inserted into this legacy projection.  The normalized
   source/approval pair is hashed separately in the receipt-only
   `provenance_hash` for every newly written receipt.  It is never added to the
   candidate dataclass, `asdict()` output or `request_hash`.
9. **Existing truth semantics.** Exact scoped fingerprint deduplication,
   claim-key conflict, explicit confirmation, supersession and resolution
   continue to use the current `TruthAction`/`TruthStatus` values and target
   checks.  New safety, scope or provenance rejections are decisions, not
   lifecycle mutations.  `commit_new`, `expected_revision`, `operation_id`,
   receipt replay and the existing success/degraded/stale mappings retain their
   public shapes.

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
- `TruthCandidate` remains the exact public pre-W-24 dataclass.  Its fields,
  order, constructor behavior for legacy arguments and `asdict()` keys/output
  remain unchanged.  Mapping-level `source`/`is_approved` metadata is kept in
  an engine-private sidecar and cannot leak into the historical request
  projection.
- A model proposal, uncertain/quoted/question content, or missing B1 approval
  cannot become canonical merely by setting `source` or `is_approved` on the
  worker path.  For the B1-enabled worker boundary, only the ReviewStore
  accept-to-`approved=True` call is treated as B1 approval; the generic truth
  engine cannot recover that proof from a `COMMITTED` mapping.  Direct API/CLI
  writes are the separately documented trusted privileged surface.  B2 remains
  deterministic grouping/order only.
  The worker still calls the same truth engine with the same operation IDs and
  validates the same canonical effect (`brain_eleven/runtime/worker.py:137-163`
  and `:733-790`).
- On a direct truth safety, scope or provenance rejection, the rejected
  candidate produces no canonical memory, lifecycle mutation, revision
  increment, backup, operation receipt, registry mutation, state mutation,
  graph/retrieval effect or direct-truth review write.  A mixed batch may retain
  the existing per-candidate decision semantics; the rejected candidate itself
  must have zero effect, and a receipt is written only under the existing
  all-eligible receipt rule.  The worker may continue its existing policy of
  routing a returned non-success outcome to B1 review; that worker-side review
  effect is outside this direct no-write assertion.
- Exact operation replay remains idempotent: the same operation ID, historical
  request hash and (when present) receipt-only provenance hash return the
  existing content-free receipt/effect without a second memory.  A changed
  candidate or provenance envelope under that operation ID remains a replay
  mismatch.  A stale `expected_revision` remains `STALE_INPUT` with no write.
- Rejected decisions and review decisions remain content-free.  Diagnostics
  may include IDs, status, reason, policy name, registry state and revisions,
  but never candidate text, secret values, raw transcript material or full
  filesystem paths.

### Registry failure result contract

Missing, archived and disabled identities are candidate policy decisions.  A
registry read failure is an authority-availability failure and must not be
collapsed into `PROJECT_UNREGISTERED`.

| Registry condition | `TruthResult.status` (dry-run / commit) | `error_code` | Per-candidate decision |
|---|---|---|---|
| ID absent from a valid registry | `SUCCESS / DEGRADED` | `None` | `REJECT / PROJECT_UNREGISTERED` |
| ID present with `status=archived` | `SUCCESS / DEGRADED` | `None` | `REJECT / PROJECT_ARCHIVED` |
| ID present, active, `proactive_capture=False` | `SUCCESS / DEGRADED` | `None` | `REJECT / PROJECT_CAPTURE_DISABLED` |
| `ProjectRegistryError`, malformed JSON/schema, or registry read `OSError` | `SCOPE_ERROR / SCOPE_ERROR` | `PROJECT_REGISTRY_UNAVAILABLE` | `REJECT / PROJECT_REGISTRY_UNAVAILABLE` |

For the last row, the result contains one bounded decision for each affected
project candidate, `source_memory_revision=None` and
`produced_memory_revision=None`; no MemoryStore load or commit is needed to
report an unavailable registry.  Global candidates do not trigger this row.
The mapping is content-free and stable even when the underlying exception
contains a path or OS message.  A `MemoryStoreCorrupt` remains the existing
`FAILED / MEMORY_STORE_CORRUPT` result and is not relabeled as a registry
failure.

## Compatibility and preserved surfaces

- `TruthAction`, `TruthStatus`, `TruthCandidate`, `TruthDecision`,
  `TruthResult`, CLI flags and result keys remain compatible.  New reason codes
  are additive; `SECRET_CONTENT`, `SCOPE_UNRESOLVED`, lifecycle reasons,
  `STALE_INPUT` and existing success/degraded mappings remain stable.
- Existing canonical records are not rewritten or reclassified.  The
  deterministic `source_id` shape `truth:<candidate_id>`, record schema,
  lifecycle fields, scope fields and retrieval inputs remain available.
- Existing operation receipts keep their `request_hash` meaning through the
  explicit legacy projection above.  New `provenance_hash` is additive; an
  old receipt without it is replayable only for a legacy-shaped request that
  omits `source` and `is_approved`.  No receipt migration write is performed
  during replay.
- `TruthCandidate` is not schema-expanded for this package: mapping metadata
  is parsed into a private sidecar, while a `TruthCandidate` object and its
  `asdict()` serialization remain byte/hash compatible with pre-W-24 callers.
- `brain_eleven.memory.truth` remains an adapter, not a second implementation;
  package/legacy/bare-loader object identity tests continue to pass
  (`tests/test_pre12_memory_state_caller_migration.py:250-265`).
- The worker's `worker.py` source, queue, extraction, operation receipt, B1
  approval and B2 grouping/order paths remain behaviorally unchanged.  Existing
  worker calls that omit the mapping metadata use the compatibility fallback
  above, and the current worker request-hash verifier remains green.  The
  contract records B1 proof at the unchanged `ReviewStore` accept call boundary
  only; a direct `COMMITTED` mapping is not relabeled as B1-approved.
- Explicit manual `brain_eleven.memory.capture.remember()` remains an explicit
  user capture path.  Its shared safety ordering and validator/store ownership
  (`brain_eleven/memory/capture.py:78-127`) are regression surfaces, not a new
  truth call or proactive-policy rewrite.
- The direct API/CLI trust assumption is explicit: W-24 tests prove the
  privileged caller contract and record provenance mapping, but do not claim
  to authenticate a process or prove that a direct caller passed through B1.
- Existing `tests/test_memory_truth.py` fixtures that use synthetic project IDs
  must register those IDs as active/enabled temporary projects, or use global
  scope, so the tests describe the new authority boundary.  No production
  fixture, registry, or historical canonical record is migrated.

## Deferred P2: `NEW` memory-ID uniqueness

The audit also identified a separate identity weakness at
`scripts/memory_truth.py:399-401`: a `NEW` candidate's caller-supplied
`successor_memory_id` is used as the new `memory_id` without a general
existing-ID collision check.  W-24 records this finding but does not fix it,
because changing ID allocation or canonical uniqueness would reopen the
MemoryStore/transaction boundary.  **Owner:** canonical-memory/truth
maintainer.  **Next package:** `W-24A-MEMORY-ID-UNIQUENESS-CONTRACT`.

The W-24 implementation report must include this item under deferred/open
findings and must not claim that the direct truth surface has full memory-ID
uniqueness until that next package is independently reviewed and shipped.

## Required tests and metrics

### Baseline and focused reproduction

- Record the exact implementation SHA separately from this contract revision,
  and preserve the baseline probe table above without printing sensitive input.
- Test all eight shared-policy secret classes from
  `tests/test_capture_safety.py:30-49`: private key, bearer token, API-key
  prefix, named client secret, password assignment, Basic authorization,
  session cookie and credential-bearing connection URL.  Every class must
  return a bounded rejection and produce zero memory/receipt/revision effect.
- Test an ordinary lifecycle content value with a secret-bearing
  `supersession`/`resolution` `note`.  The decision must be
  `REJECT / SECRET_CONTENT`, the target status/note/revision and canonical
  bytes must remain unchanged, and no successor or operation receipt may be
  created.  Repeat the test for a non-secret note control and for each shared
  non-secret policy limit.
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
  commitment gate.  Test the scoped B1 transition explicitly: an input with
  no commitment passed to `_memory_candidate_values(candidate, approved=False)`
  yields `UNCERTAIN` and a truth `REVIEW_REQUIRED /
  UNCOMMITTED_CANDIDATE` decision; after `ReviewStore` accept, the unchanged
  service calls worker `apply_candidate(..., approved=True)` and the same
  effect applies with `COMMITTED`, exactly once.
- Test the direct privileged distinction with the same field-shaped
  `COMMITTED` mapping passed straight to `MemoryTruthEngine.process()`: it may
  be accepted under the documented trusted boundary, but its result must carry
  no B1-approved claim or inferred ReviewStore proof.  The test must document
  that the generic engine cannot distinguish this mapping from a pending B1
  record and must not assert B1 exclusivity for the direct call.
- Missing/invalid source, non-boolean approval, explicit approval false,
  non-`COMMITTED` commitment, contradictory project label and global/project
  identity cases are covered.  A contradictory project label is normalized to
  the registry label; a global `project_id`, `project` or `project_label` is
  rejected with `GLOBAL_PROJECT_METADATA`.  None may bypass safety or registry
  authority.
- Malformed registry JSON, an unsupported registry schema and a simulated
  registry read `OSError` each produce `SCOPE_ERROR /
  PROJECT_REGISTRY_UNAVAILABLE` with a per-project
  `REJECT / PROJECT_REGISTRY_UNAVAILABLE` decision, no path/exception text,
  and no MemoryStore read/write side effect.  Missing, archived and disabled
  projects retain their distinct per-candidate reasons and dry-run/commit
  statuses from the result table.
- Build a schema-version-3 pre-W-24 canonical receipt with the exact legacy
  request hash and no `provenance_hash`.  Replaying the same legacy-shaped
  candidate and operation ID must return the existing decision/effect with no
  revision, byte or receipt change.  Supplying `source` or `is_approved` to
  that old receipt must return `INVALID_INPUT /
  OPERATION_REPLAY_MISMATCH` with no write.
- Commit a new candidate with explicit user provenance, replay it unchanged,
  then change only `source` or `is_approved`; the unchanged call replays once,
  while the changed envelope mismatches through `provenance_hash` and cannot
  create a second effect.  The worker-shaped legacy payload must continue to
  satisfy the existing worker effect-verification hash.
- Assert that `dataclasses.fields(TruthCandidate)` and the ordered keys from
  `asdict(TruthCandidate.from_mapping(legacy_mapping))` are exactly the
  historical field list; neither `source` nor `is_approved` may appear.  Pass
  both a legacy `TruthCandidate` object and its mapping through the engine and
  assert equal legacy request hashes and decisions.  A mapping carrying the
  new metadata may produce a private sidecar and receipt `provenance_hash`,
  but must leave the public object/asdict/hash shape unchanged.
- Run the existing worker-shaped apply/verification control without editing
  `brain_eleven/runtime/worker.py`: its receipt `request_hash` must equal the
  expected hash recomputed at `worker.py:512-519`, and a replay must verify the
  same canonical effect exactly once.
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
   or provenance authority.  The public `TruthCandidate` dataclass and
   `asdict()` shape are unchanged, `worker.py` is byte-unchanged, and the
   changed-file list is limited to this package's truth surface and focused
   tests.
2. **Safety/scope proof:** all eight secret classes, lifecycle-note secret
   cases and all three negative registry states reject with zero canonical,
   registry, receipt, direct-truth review, state, graph or retrieval effects;
   malformed/read-failed registries use the explicit unavailable mapping;
   active/enabled user and worker controls commit exactly once with the
   expected provenance.
3. **Compatibility proof:** focused truth, package identity, migration,
   capture-safety, manual capture, worker/B1 and B2 tests pass; existing
   lifecycle, dedup, retrieval, pre-upgrade receipt replay, dataclass/asdict
   parity and worker request-hash verification, and Phase 20 frozen/V2 shadow
   assertions remain unchanged.  The direct API/CLI privileged assumption is
   reported as a boundary limitation, not a failed B1 proof.
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
- No `brain_eleven/runtime/worker.py` change, queue, evidence, extraction,
  model, B1 review, B2 ordering, `StateBoundary`, manual capture, graph or
  retrieval implementation change.  In particular, no worker verifier
  workaround may be used to hide a changed `TruthCandidate`/`asdict()` shape.
- No second safety regex, secret-pattern tuning, source authentication system,
  transcript provenance redesign or project-root/ID migration.  Root/ID
  mismatch work remains W-13 scope.
- No direct API/CLI caller authentication or ReviewStore approval-token proof;
  those calls remain a trusted privileged boundary by contract, while B1
  governs worker-generated proposals only when enabled.
- No rewrite, repair or backfill of historical records with the old source or
  approval values; no canonical schema migration is introduced for the
  mapping-only provenance inputs or receipt-only `provenance_hash`.
- No closure of the deferred `NEW` memory-ID collision finding; that belongs to
  owner `canonical-memory/truth maintainer` in
  `W-24A-MEMORY-ID-UNIQUENESS-CONTRACT`.
- No change to lifecycle policy, dedup ranking, claim conflict rules, API
  response design, CLI flags, V2 promotion/default rollout or Phase 20.
- No automatic project registration, archive reactivation, proactive opt-in
  change, review bypass, state mutation or model-to-memory authority grant.

## Package report template

```text
PACKAGE: W-24
CONTRACT REVISION: 091e064b0a4e95b6f6fbe4c1cc97932d0d7900f0
AUDIT BASELINE: 0ad5fe5d118c03df1d8b0e0a258e2dadf13f5b8b
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
                        hardcoded provenance count, lifecycle-note bypass count
QUALITY METRICS AFTER: 0 secret bypasses, 0 unregistered/archived/disabled
                       effects, 0 lifecycle-note secret effects, normalized
                       user/worker provenance
SAFETY METRICS: zero rejected-candidate writes; zero sensitive output; zero
                registry/state/review/receipt side effects on rejection
SCOPE METRICS: active/enabled acceptance; negative registry reason counts;
               registry-unavailable mappings; cross-project and global controls
IDEMPOTENCE/CAS: legacy pre-upgrade replay, provenance mismatch, replay/effect
                 IDs, revision deltas, mismatch and stale counts
PUBLIC SHAPE/PARITY: historical TruthCandidate fields/order/asdict and worker
                     request-hash verifier remain unchanged
B1 TRANSITION METRICS: unapproved UNCERTAIN review-required count, ReviewStore
                       accept-to-approved COMMITTED count, direct privileged
                       COMMITTED count with no B1 proof inference
DEFERRED P2: NEW caller-supplied memory-ID collision — owner canonical-memory/
             truth maintainer; next package W-24A-MEMORY-ID-UNIQUENESS-CONTRACT
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
