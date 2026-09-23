# IG04-B3 — Review-Queue Nudge Contract

**Status:** FROZEN FOR IMPLEMENTATION — owner-approved scope revisions recorded
2026-09-23. The implementation remains subject to exact-head CI and independent
read-only review; the implementer does not approve the package.

**Package:** IG-04, Branch B, sub-package B3 (review-queue SessionStart nudge)

**Implementation owner:** Codex.

**Program boundary:** Phase 20 remains FROZEN / LOCKED and V2 remains SHADOW.
This package extends the B1 human-approval boundary and B2 review-queue
usability only.

## Purpose

A captured candidate cannot affect retrieval until a human accepts it. B3 adds
one content-free, rate-limited line through the existing V1 SessionStart
renderer to make pending review visible after a substantive session. The
trigger is a **project with one or more visible, pending B2 review groups after
a session with at least five submitted prompts**. It is not “memory was not
updated”: in SHADOW, no automatic canonical write is expected, so that trigger
would fire routinely and cause alert fatigue.

The existing V1 SessionStart renderer uses English headings; the nudge uses
English, for example: “3 candidates are waiting for review.” It includes no
candidate content.

## Owner-approved scope revisions

The owner explicitly approved the following bounded deviations from the
original B3 goal on 2026-09-23:

1. A content-free, project-scoped pending-review metadata index/sidecar and
   review-queue lifecycle changes to maintain it are in scope. This is
   operational metadata in the existing review directory; it is not canonical
   memory or state.
2. Because Claude and Codex `Stop` hooks are turn-scoped, preserve the counter
   through `Stop` and finalize it only at the per-session `SessionEnd` event.
   Clearing it on each `Stop` would make the five-prompt threshold
   unreachable.

The bounded Phase 0 evidence and exact sources are recorded in
[`IG04-B3-AUDIT-NOTE.md`](../history/evidence/IG04-B3-AUDIT-NOTE.md). No other
scope expansion is authorized.

## Hard invariants

- **No new framework or agent behavior.** This is a bounded convenience line.
- **Canonical authorities are unchanged.** B3 writes no canonical memory or
  project state. Its only persisted data is content-free runtime counters and
  markers plus the approved content-free review metadata index and its
  recoverable transaction intent.
- **One SessionStart owner.** Render only through the existing V1 SessionStart
  renderer and include the line in its existing budget and final scope,
  revision, safety and mode rechecks. Hooks never print free text directly
  into a session.
- **Content-free state and output.** Counters, markers, index, transaction
  intent, telemetry and the rendered line contain only bounded IDs/hashes,
  status, counts and timestamps. They contain no prompt or candidate text and
  no filesystem paths. The B3 counter branch does not inspect or retain the
  prompt field. The existing UserPromptSubmit capture path may continue its
  already-authorized transient prompt processing unchanged.
- **Fail-closed nudge; fail-open session.** Missing/invalid project, disabled
  opt-in, OFF mode, invalid marker/index, lock timeout, unavailable queue,
  budget overflow or any B3 exception yields no nudge and never blocks or
  delays a session. If the queue count is unknown, preserve a still-valid
  marker for a later SessionStart; do not guess zero.
- **No candidate-body access from SessionStart.** The SessionStart path reads
  the B3 marker ledger and the ready metadata index only. It must not open
  `rev_*.json`, call `ReviewStore.list()` or `expire()`, or rebuild/reconcile
  the index.
- **Project isolation.** A prompt counter and marker are keyed by stable
  session identity and project ID. A marker for project A is never visible in
  project B. Unknown or non-opted-in projects create no counter or marker.
- **Opt-in is required.** Respect
  `.claude/remember-config.json` → `proactive_opt_in_projects` and the
  registered project identity; paths are resolved only by existing project
  ownership logic and are never persisted in B3 state.
- **No rollout change.** OFF suppresses all B3 counting, finalization and
  delivery. SHADOW, CANARY and ACTIVE retain their existing gates. B3 does not
  change any threshold, gate, skip, HOLDOUT result, IG01 evaluation package or
  V2 SHADOW behavior.
- **Windows and verification UX.** Native launchers stay windowless. Tests and
  verification do not open browser panels or console windows.
- **No repository-root additions.** Follow DOCUMENTATION-AUTHORITY; every new
  document reference is added to PROJECT-STATUS and DOCUMENTATION-AUTHORITY in
  the same documentation commit.
- **No unrelated package.** Do not start or change another package.

## Preconditions

1. Branch `ig/ig04b3-review-nudge`, based on exact-green master head
   `6142c2c02d5ea13d1260f0ce10597918f58c4afc`; master Validation run
   [`35820195178`](https://github.com/WinierKingYT/Brain-Eleven/actions/runs/35820195178)
   passed on both operating systems. Recheck the latest master status before
   final integration; an artifact-upload-only 403 is infrastructure noise and
   requires rerunning the failed job.
2. The completed read-only Phase 0 audit is committed as
   `docs(ig04b3): complete phase zero audit`. Its only remaining unverified
   items are live native-client hook trust, Codex latency and post-change
   measurements; these are limitations to report, not reasons to claim
   verification.
3. No source, tests, hook configuration or threshold may change until this
   contract is committed.

## Frozen constants and data model

Define and document these constants in one module:

| Constant | Value | Meaning |
|---|---:|---|
| `MIN_PROMPTS_FOR_NUDGE` | 5 | Minimum valid UserPromptSubmit events for one session/project counter |
| `COUNTER_TTL` | 7 days | Remove abandoned counters that never receive SessionEnd |
| `MARKER_TTL` | 7 days | A session-end marker's maximum lifetime, matching B1 proposal expiry |
| `MAX_NUDGES_PER_SESSION_START` | 1 | Maximum rendered B3 lines for one SessionStart invocation |

Use the existing operational service-state root
`<vault>/.brain-eleven/runtime` for the B3 counter/marker ledger. It may contain
only schema version, session hash, project ID, integer prompt count and UTC
timestamps. Use an existing cross-process lock and atomic JSON writer; handle
all counters for one session hash under the same bounded lock. Do not persist
raw session IDs or cwd paths.

Use the existing review queue directory
`<vault>/.brain-eleven/runtime/review` for a content-free metadata index and
its transaction intent. The index contains schema/readiness and generation
metadata plus, per review ID, only project ID, lifecycle status, expiry time
and the existing B2 content fingerprint. Do not duplicate candidate bodies or
paths. Treat the B2 fingerprint as an opaque content-derived hash.

The nudge's pending count is the number of **visible B2 groups** for the
resolved project: distinct `(project_id, content_fingerprint)` values with at
least one member whose lifecycle status is PENDING and whose seven-day expiry
is in the future. Raw duplicate records count once; terminal or expired
records count zero. The deterministic B2 primary ordering does not affect this
count.

## Frozen flow

### 1. UserPromptSubmit

For every valid submitted prompt, resolve the same registered, opted-in
project identity used by V1 and read only the event's stable `session_id`
metadata for the B3 branch. Compute a domain-separated stable hash of that ID;
never persist the raw ID. Atomically increment the counter keyed by
`(session_hash, project_id)`, with a UTC last-seen timestamp and bounded TTL.
The counter stores no prompt text, request hash, transcript path or cwd path.

If session ID is missing/invalid, project is unknown/unregistered/not
opted-in, runtime config is invalid, or mode is OFF, do not count. A lock or
state failure is degraded convenience behavior and does not block the prompt.
Existing capture behavior on this event remains unchanged.

### 2. Stop and SessionEnd

`Stop` is per-turn on both clients. It does not clear, finalize, or otherwise
mutate the B3 counter. The current B1 Stop enqueue path remains unchanged.

At `SessionEnd`, use its stable session ID to find every counter for that
session hash, retaining each counter's stored project ID (a session may have
changed cwd). Under the B3 state lock:

- For each still-registered and opted-in project in a non-OFF runtime, create
  or upsert one deterministic marker for that session/project if
  `prompt_count >= MIN_PROMPTS_FOR_NUDGE`. The marker contains
  `schema_version`, `project_id`, `session_id_hash`, `prompt_count`,
  `ended_at`, and `expires_at`; it contains no content or paths.
- Below threshold, or if the project is no longer eligible, create no marker.
- Delete the processed counter in either case. Duplicate SessionEnd delivery
  is idempotent: one session/project cannot create multiple markers.
- Expire abandoned counters after `COUNTER_TTL`; expired counters never create
  markers.

The SessionEnd finalizer is an independent best-effort hook-boundary action.
It must not depend on transcript availability, candidate extraction, queue
success, or the worker's Stop/SessionEnd queue mapping. Failures are swallowed
as degraded convenience behavior.

Claude Stop may not run after an interrupt; SessionEnd is still the cleanup
point. Codex SessionEnd can be delayed until the session terminates or becomes
idle. Therefore the nudge may be delayed until the next actual SessionStart;
do not substitute per-turn Stop to accelerate it.

### 3. Review metadata index

Maintain the index on every queue lifecycle mutation: proposal add, per-record
expiry, grouped accept/reject, and any supported delete/import/migration. All
writers coordinate under the existing review index lock. B2's
`duplicate_of`/`duplicate_status` annotations are not index lifecycle
statuses; visible groups are recomputed from project ID and fingerprint.

Record and index files cannot be jointly committed by the existing atomic
writer. Use a content-free durable intent/recovery protocol (or a demonstrably
equivalent generation-checked transaction) under the same lock:

1. Persist an intent with the operation and complete target index metadata,
   but no candidate text or path.
2. Apply the queue-record transition using the existing B1 lifecycle and
   atomic write rules.
3. Atomically apply the index generation.
4. Clear the intent.

Recovery is idempotent and runs only on review-queue owner paths. While an
intent is pending, the metadata index is not ready for a nudge. SessionStart
checks readiness and fails closed if an intent, corrupt schema, inconsistent
generation or lock failure exists; it never attempts recovery or body-based
rebuild.

For pre-index/legacy queues, the existing full review-list path may rebuild
and mark the metadata index ready while it already reads the records.
SessionStart must not trigger this migration. Until an explicit queue-list
rebuild has completed, the unknown count produces no nudge; this one-time
rollout limitation is reported. A rebuild must preserve B1 lifecycle and B2
grouping semantics.

### 4. SessionStart through V1

Resolve the current registered, opted-in project and V1 output as today. A
SessionStart may load a non-expired marker for that exact project and query the
ready metadata index for its visible pending-group count. Never call
`ReviewStore.list()` or `expire()` from this path.

- No marker or an expired marker: no line; remove the expired marker.
- Valid marker with known count zero: no line; consume/discard the marker.
- Valid marker with a positive count: offer exactly one optional line to the
  V1 renderer and include it only if the existing safety, budget, revision,
  scope and mode checks all pass. Count the line inside the current V1 budget.
- Unknown/unreadable index or queue error: no line; retain an unexpired marker
  for a later retry.
- Budget overflow or failed final V1 recheck: omit the line and retain the
  marker until a successful delivery or expiry.
- On successful V1 delivery, atomically consume all eligible markers for the
  current project so repeated/duplicate SessionStart handling cannot repeat
  the same nudge. Coalesce multiple markers into the same single line/count.

If marker consumption cannot be committed, omit the line. The feature is
at-most-once convenience behavior; it must not risk duplicate or blocking
output. V1 output without a valid marker remains byte-for-byte unchanged.

## Implementation commits

Keep each commit narrow and ordered:

1. `docs(ig04b3): contract` — this frozen contract and its status/authority references.
2. `feat(review): content-free pending index` — metadata index, transaction intent/recovery and queue lifecycle tests.
3. `feat(hooks): per-session content-free prompt counter` — stable session hash, atomic count and focused tests.
4. `feat(hooks): session-end nudge marker` — Stop preservation, SessionEnd finalization, TTL and tests.
5. `feat(v1): SessionStart review nudge` — optional budgeted line, scoped count and delivery/consumption tests.
6. `test(ig04b3): integration, windows and latency` — isolation, concurrency, failure, regression and same-machine latency comparison.
7. `docs(ig04b3): package report and dataflow` — report, RUNTIME-DATAFLOW node, PROJECT-STATUS and DOCUMENTATION-AUTHORITY update; explicitly distinguish configured from delivered and verified from unverified.

## Required tests (Ubuntu and Windows CI)

- **Index semantics:** visible count equals distinct project/fingerprint groups
  with a pending unexpired member; raw duplicate records count once; expired,
  terminal, unknown-project and foreign-project entries do not count.
- **Content boundary:** SessionStart reads only marker and metadata-index files;
  tests fail if it calls `ReviewStore.list()`, `expire()`, or reads a
  `rev_*.json` body. No prompt/candidate text or filesystem path appears in
  sidecars, intents, telemetry or rendered output.
- **Index lifecycle:** add, single expiry, grouped accept/reject, list-driven
  expiry, legacy index rebuild and idempotent recovery. Inject interruption
  after each transaction step and prove SessionStart fails closed until
  recovery. No duplicate group leaks across projects.
- **Counter:** one increment per valid UserPromptSubmit event; concurrent
  sessions in one vault do not interfere or lose updates; concurrent writers
  do not lose increments; missing/invalid session ID and unknown/non-opted-in
  project do not count.
- **Session threshold/lifecycle:** four prompts produce no marker; five
  produce one; Stop never deletes/finalizes; duplicate Stop and SessionEnd
  remain idempotent; SessionEnd finalizes every project counter for the
  session; expired counter creates no marker.
- **Delivery:** marker plus pending count > 0 yields exactly one line; raw B2
  duplicates are reported as visible groups; count zero consumes marker
  without output; no/expired marker gives no line; same marker is never
  repeated; multiple markers coalesce to one line; an unknown index preserves
  the marker without output.
- **Isolation and opt-in:** project A marker/counter never appears in B;
  non-opted/unregistered project does nothing.
- **Budget and V1 compatibility:** line counts inside V1's existing budget;
  overflow/final recheck behavior is unchanged; all existing V1 tests pass
  unmodified in behavior and absent-marker output is unchanged.
- **Failure:** corrupt/unreadable runtime state or index, unresolved intent,
  lock timeout, queue unavailable or marker write failure means session
  starts normally with no nudge and no surfaced exception.
- **Modes:** OFF suppresses B3; SHADOW/CANARY/ACTIVE follow the existing
  documented gates with no threshold or gate changes.
- **Windows:** launchers remain windowless and create no console process.
- **Latency:** rerun the same isolated W-07B harness on the same host after the
  change and report before/after p50/p95 by event. Baseline is in
  `IG04-B3-AUDIT-NOTE.md`; its Claude samples are not Codex evidence. Do not
  change the existing gates or claim broader W-07B gates pass.
- **Regression:** full existing test suite and exact-head remote Validation
  remain green on Ubuntu and Windows; no tests skipped and no CI relaxation.

## Exit criteria

All are required before requesting independent review:

1. Full local regression passes; focused new tests pass on Ubuntu and Windows.
2. Remote Validation is green at the exact final head on both OS; report its
   URL and SHA. Recheck the master precondition before final integration.
3. No canonical write is added or called by changed B3 files; the reviewer can
   verify this in the diff and import/call graph.
4. Same-host before/after latency results are reported without asserting that
   Codex or native hook trust was verified if it was not.
5. Package report lists verified vs configured-only behavior, limitations,
   deferred items with reasons, and the fact that users must open the review
   queue to rebuild a legacy metadata index.
6. `RUNTIME-DATAFLOW.md` records B3 state and marks native trust ACTIVE only
   where actually verified; configured does not imply delivered.
7. No forbidden changes to thresholds, gates, HOLDOUT, IG01, V2, canonical
   stores or repository-root files.
8. Stop after implementation/evidence and request a separate independent
   read-only review. Do not self-approve or mark SHIP.

## Explicitly deferred

- “No canonical effect this session” as a trigger: always true in SHADOW and
  would create routine, noisy reminders.
- Automatic candidate acceptance, direct hook text, any UI beyond this one
  line, or changes to V1 ownership.
- Codex live native trust and Codex-specific latency unless separately
  verified in a safe, isolated environment.
- A SessionStart-triggered or hook-triggered migration/rebuild that reads
  candidate records.

## Final report format

Report changed files and why; tests added and executed with results; latency
before/after; exact final-head CI run URL and SHA; limitations (including
native trust if unverified and the need to open the queue once for legacy
indexing); deferred items and open questions. Then stop and request independent
read-only review.
