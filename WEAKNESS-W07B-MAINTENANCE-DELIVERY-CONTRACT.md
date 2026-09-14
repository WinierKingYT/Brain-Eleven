# W-07B Contract — Native Maintenance and Reminder Delivery

**Status:** BOUNDED CONTRACT / INDEPENDENT REVIEW PENDING  
**Priority:** P2 continuity/runtime reliability  
**Target:** native SessionEnd maintenance trigger and SessionStart report delivery  
**Phase 20:** FROZEN / LOCKED  
**V2 runtime:** SHADOW

**Review boundary:** This revision is contract-only. Its review must assess
the bounded problem, safety invariants, evidence matrix and exit gate. The
absence of implementation and new tests is expected here and is not an
implementation verdict.

## Evidence-backed problem

The native launcher currently enqueues Stop/SessionEnd capture and starts the
worker service, but neither the native worker path nor SessionStart invokes or
consumes the packaged post-session maintenance report. The legacy
`session_pipeline.py` path can run maintenance separately, but that does not
prove native delivery. Existing reports are not bound to the active project
or the current canonical revision, maintenance steps read separate snapshots,
repeated runs have no durable revision idempotency, and reports can retain raw
memory content or exception strings. Stop and SessionEnd are also not
distinguished for maintenance triggering.

## Objective

Make native maintenance delivery observable and safe without changing the
maintenance algorithms, canonical authorities, retrieval ranking or hook
latency contract:

`SessionEnd` capture terminal effect → durable maintenance intent → background
maintenance run → project/revision-bound privacy-safe report → matching
`SessionStart` bounded reminder context.

## Bounded scope

The implementation may touch only the native runtime coordination and its
focused tests:

- `brain_eleven/runtime/launcher.py`, `worker.py`, `service.py`, `context.py`
  and the packaged maintenance/report projection as needed;
- a small durable maintenance-intent/receipt surface under the existing
  runtime directory;
- native hook, worker, maintenance and context tests plus package evidence.

The existing `scripts/session_pipeline.py` manual/legacy path remains
compatible and is not used as proof of native delivery. Maintenance execution
must be asynchronous after the SessionEnd capture reaches its terminal queue
state; the hook must not read transcripts, run graph/anomaly/digest work, or
wait for maintenance.

## Trigger and event semantics

- `SessionEnd` is the only native event that creates a maintenance intent.
- `Stop` continues to enqueue capture only and never creates a maintenance
  intent; duplicate Stop events remain harmless.
- The intent key must include opaque project identity and the trusted event or
  capture receipt identity. It becomes eligible only after the worker has a
  verified terminal capture/effect receipt (including an explicit zero-effect
  terminal result where applicable).
- A worker/service restart must resume an intent exactly once. A crash before
  report publication leaves the intent retryable; a crash after publication
  leaves a durable receipt and does not rerun the same work.
- Maintenance failure is visible through a content-free status/error code and
  never blocks or changes the canonical capture effect.

## Freshness, scope and report contract

Every native report must carry at least:

- schema/version and report status;
- opaque `project_id` (or an explicit global marker, never an inferred
  project); session/event identity hashes;
- `source_memory_revision` and the relevant state/graph revision observed
  before publication;
- generation timestamp and a durable intent/run identity;
- privacy-safe counts, IDs/hashes and bounded summaries only.

The report is fresh for SessionStart only when its project identity matches the
trusted current project and its recorded source revisions still match the
canonical stores required by the report. Missing, stale, failed, corrupt or
cross-project reports are exposed as bounded status but never injected as
reminder context. A report for one project must not be visible in another
project's SessionStart response.

Raw memory text, transcript text, prompts, absolute transcript paths and raw
exception strings are forbidden in durable reports, ledgers and telemetry.
Failures use stable content-free error codes. The context addition is bounded
by a fixed byte/token limit and cannot replace the normal V1/V2 context path.

## Idempotence and authority invariants

- The durable intent/receipt is the sole maintenance execution identity;
  repeated SessionEnd delivery and worker retries do not duplicate reports or
  graph/anomaly/digest side effects.
- Maintenance remains derived/read-only with respect to `MemoryStore`,
  `StateStore` and `ProjectRegistry`; it must not publish canonical memory,
  state or authority changes.
- Existing queue locks, receipt ordering, project isolation and model-output
  versus truth boundaries remain unchanged.
- Report publication is atomic and a partial report is never consumed.
- Existing manual maintenance behavior and CLI flags remain parity-compatible.

## Required evidence and tests

New focused tests must prove:

1. SessionEnd creates one durable intent only after terminal capture; Stop
   creates none.
2. Intent replay, worker crash before/after report publication and service
   restart yield one report and no duplicate derived work.
3. Report freshness rejects changed memory/state revisions, missing/corrupt
   reports and wrong-project reports; matching reports are delivered once at
   SessionStart.
4. Report/context payloads contain no raw memory, prompt, transcript path or
   exception string and obey the fixed size bound.
5. Maintenance failure is visible, retryable and non-blocking; canonical
   stores and queue receipts remain unchanged.
6. Existing maintenance, session pipeline, native hook, worker and context
   suites pass without weakening their assertions; manual CLI parity remains.

Acceptance also requires critical flake8 (`E9,F63,F7,F82`), compileall,
`git diff --check`, full regression, content-free evidence and an independent
read-only implementation review returning exactly `SHIP`, `FIX-FIRST` or
`RETHINK`.

## Explicitly out of scope

No new retrieval/ranking or semantic extraction, no V2 promotion, no Phase 20,
no automatic writes to `Daily.md`, `Threads.md`, `Last Session.md` or open-loop
Markdown, no changes to canonical persistence implementations, no prompt or
transcript retention, no cross-project inference, and no redesign of the
legacy `session_pipeline.py` maintenance sequence.

## Exit gate

W-07B remains `FIX-FIRST / NOT ACCEPTED` until the exact-head trigger,
freshness, idempotence, project isolation, privacy, latency and failure
evidence all pass and an independent reviewer returns `SHIP`.

