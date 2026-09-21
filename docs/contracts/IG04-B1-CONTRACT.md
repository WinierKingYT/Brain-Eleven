# IG-04-B1 — Human-Approved Retrieval Contract

**Status:** APPROVED — HUMAN CHECKPOINT PASS (2026-09-10)

**Package:** IG-04, Branch B1 (automatic capture with human-approved retrieval)

**Implementation authorization:** Ahmet explicitly approved this contract on
2026-09-10. Implementation owner: Codex. The accepted review surface is the
existing local `/review` UI/API. Lifecycle names are `PENDING`, `ACCEPTED`,
`REJECTED` and `EXPIRED`; the single rollback switch is
`b1_human_approval=false`.

**Program boundary:** Phase 20 remains FROZEN / LOCKED and V2 remains SHADOW.

## Objective

B1 makes automatically captured knowledge safe for daily use by separating
candidate capture from retrieval eligibility. The system may collect a bounded
candidate automatically, but a candidate must pass an explicit human decision
before it can become canonical knowledge and appear in future context.

The existing canonical authorities remain the only authorities:

* `MemoryStore` owns canonical memory history.
* `StateStore` owns mutable project state.
* `ProjectRegistry` owns project identity and scope.

No model output, queue record or review record is canonical truth.

## Current path and B1 boundary

The current automatic SessionStart path is V1:

```text
SessionStart
  → runtime launcher/service
  → scripts/context-compiler.py
  → scripts/hybrid-search.py
  → V1 context output
```

B1 changes the **retrieval eligibility boundary** of this path:

1. V1 may retrieve only active canonical records that have passed human
   approval, plus the existing explicitly allowed global/project records.
2. A pending, rejected, quarantined or otherwise non-canonical candidate must
   never be injected by SessionStart or UserPromptSubmit.
3. The V1 compiler and hybrid-search candidate generation remain the bounded
   producer for this package. B1 does not replace their ranking algorithm,
   add embeddings, or tune retrieval weights.
4. Existing automatic capture continues to emit bounded candidates through the
   current queue/evidence/extraction path. B1 adds the approval state boundary;
   it does not introduce a new capture pipeline.

The following remain unchanged:

* V2 router/compiler and all V2 shadow comparisons;
* project scope resolution and fail-closed behavior;
* MemoryStore, StateStore and ProjectRegistry schemas and authority rules;
* deterministic safety filtering, secret filtering and evidence retention;
* Claude/Codex hook event names and their bounded latency behavior;
* existing canonical records that are already active and approved.

Any change outside this boundary requires a separate package contract.

## Candidate lifecycle

Every B1 candidate has a stable candidate identity, project scope, evidence
references, candidate type, content fingerprint and lifecycle timestamps. The
minimum lifecycle is:

```text
CAPTURED → PENDING_REVIEW → ACCEPTED → CANONICAL
                         └→ REJECTED
```

`PENDING_REVIEW` is review data, not retrievable knowledge. `ACCEPTED` means
the human decision passed deterministic validation; the canonical write and
its receipt must still be completed before the candidate becomes `CANONICAL`.

An acceptance must use the existing authority boundary and an idempotent
operation identity. A replay must return the existing receipt and must not
create a second memory or state record.

## Human experience

Human approval is an explicit, separate review action. SessionStart and
UserPromptSubmit remain non-interactive and must never wait for a person or
open a window.

The primary review surface is the existing local review UI/API (`/review` and
its review-candidate endpoints). A CLI adapter may expose the same operations,
but it must not create a second approval authority or a second storage format.
The rollout switch is exposed by the existing CLI as
`python -m brain_eleven --vault <vault> approval ON|OFF`; it changes only the
B1 boundary and does not change the runtime mode.

Each pending item shown to the user contains only bounded review information:

* candidate ID and project label;
* proposed type and content needed for the decision;
* evidence reference/role and a short bounded reason;
* created time and current lifecycle status;
* accept/reject controls, with an optional safe edit if the existing review
  contract permits it.

Raw transcripts, secrets, tokens and unrelated project content are not shown
or stored as review telemetry. The review surface must make project scope
visible before the user accepts an item.

Accepting an item requires an explicit action. The action is validated against
the current canonical revision and produces a content-free receipt containing
the operation identity, resulting canonical effect and project scope.

Rejecting an item also requires an explicit action. There is no implicit
approval caused by timeout, retrieval, restart or a new session.

## Rejection and replay guarantee

A rejected candidate is durably marked `REJECTED` with a bounded rejection
reason, candidate fingerprint, project scope and evidence identity. It is not
eligible for retrieval and is not proposed again when the same capture event
is replayed, delivered twice or reprocessed after a worker restart.

The same candidate fingerprint in the same project remains suppressed. A later
candidate may be proposed only when its content/evidence fingerprint is
materially different or a user explicitly reopens the rejected item. Rejection
must not silently delete the evidence needed to explain the decision.

## Safety and authority invariants

* Pending and rejected candidates have zero retrieval eligibility.
* A project-scoped candidate cannot be accepted into another project.
* An approval cannot bypass secret filtering, schema validation, lifecycle
  checks, CAS/revision checks or canonical receipts.
* The model may propose a candidate but can never accept it or write directly
  to a canonical store.
* Acceptance and rejection are idempotent; duplicate actions return the
  existing terminal result.
* An ambiguous or malformed candidate is quarantined for review and is never
  guessed into canonical truth.
* B1 does not change V2 rollout, Phase 20 status or the canonical authority
  boundary.

## Acceptance criteria

B1 is complete only after the following evidence exists on one exact revision:

1. **Eligibility:** active approved canonical records can be retrieved;
   pending, rejected and quarantined candidates cannot appear in either V1
   hook output.
2. **User action:** the review UI/API lists scoped pending candidates and an
   explicit accept action creates exactly one verified canonical effect.
3. **Rejection:** reject persists a terminal status and the same event replay
   does not recreate or re-propose the candidate.
4. **Crash/replay:** acceptance before/after canonical write, duplicate queue
   delivery, worker restart and CAS conflict are replay-safe with no duplicate
   effect and no silent success.
5. **Safety:** wrong-project retrieval, forbidden content, rejected content
   and inactive lifecycle records have zero leakage; secret content is absent
   from review telemetry.
6. **Runtime:** SessionStart remains non-interactive, bounded and rollbackable
   to the pre-B1 V1 behavior with one configuration switch.
7. **Regression:** existing capture, memory, state, authority, router and
   compiler suites remain green; a focused B1 E2E test covers capture → review
   → accept/reject → retrieval.
8. **Review:** an independent read-only reviewer returns `SHIP`. A self-review
   by the implementer is not independent evidence.

Required metrics are reported separately for accepted, rejected and pending
items. Retrieval quality must not be presented as improved merely because
unapproved candidates were hidden; the pre-B1 V1 baseline remains the
comparison point.

## Rollout and rollback

B1 is disabled by default until its package gate passes. Rollout proceeds only
after focused tests, full regression and independent review. A single feature
configuration must restore the pre-B1 V1 eligibility behavior without schema
rollback or data deletion. Rejected decisions and canonical receipts remain
auditable after rollback.

## Explicitly out of scope

This package does not include:

* V2 promotion, V2 ranking changes, embedding-provider migration or task-aware
  retrieval tuning;
* semantic extraction, model selection, confidence calibration or correction/
  reference-resolution intelligence;
* a new queue, worker, persistence authority, graph reasoner, planner or agent
  framework;
* automatic acceptance, direct model writes, cross-project globalization or
  automatic Phase 20 unlock;
* redesigning `context-compiler.py`, `hybrid-search.py` or hook protocols
  beyond the approval eligibility check;
* deleting historical evidence or changing the existing privacy-retention
  contract;
* Phase 20 work of any kind.

## Required human checkpoint

Ahmet must review and approve this contract before implementation begins. The
approval record must name the accepted review surface, lifecycle status names,
rollback switch and implementation owner. Until that checkpoint is recorded,
`IG04-B1-CONTRACT.md` remains a draft and B1 remains unopened.
