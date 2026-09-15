# W-07B-R1 Contract — Native Evidence Harness Repair

**Status:** APPROVED CONTRACT / implementation complete; independent review pending
**Package:** W-07B-R1 evidence-only closure  
**Priority:** P2 evidence integrity  
**Phase 20:** FROZEN / LOCKED  
**V2 runtime:** SHADOW

This is a bounded follow-up to the approved W-07B runtime acceptance plan. It
changes no production runtime behavior, hook installation, canonical store, or
live client configuration. The package exists because the current evidence
harness cannot produce valid latency evidence and its process tests do not
exercise every process boundary required by the parent plan.

## Evidence-backed gaps

1. `evals/runtime_benchmark.py` creates transcripts in its temporary directory
   but does not bind that directory through `RuntimeConfig.transcript_roots`.
   `capture_provenance.resolve_transcript_path()` therefore rejects every
   synthetic Stop path as outside the configured native root and the benchmark
   fails with a generic degraded result.
2. The benchmark measures only direct launcher Stop/UserPromptSubmit calls. It
   does not implement the approved Claude/Codex × SessionStart,
   UserPromptSubmit, Stop and SessionEnd × cold/warm matrix.
3. `tests/test_w07b_process_recovery.py` uses direct delivery calls for most
   boundaries. It proves useful intent recovery, but does not independently
   kill and restart a worker process after each required durable boundary.
4. The committed W-07B evidence report is bound to an older evidence head and
   does not describe the current runtime dependency graph. A new report must
   bind every claim to one exact implementation and harness revision.

## Bounded objective

Produce reproducible, content-free evidence on the current exact head by:

- fixing the synthetic benchmark fixture so its temporary transcript roots are
  explicitly configured and remain isolated;
- adding test-only deterministic process barriers for worker claim,
  maintenance staging, report publication and final receipt recovery;
- adding a latency harness that records only elapsed milliseconds, status and
  opaque identifiers, with p50/p95 calculated per required client/event/
  cold/warm cell;
- providing an isolated native-client runner contract that can report
  `VERIFIED` only after the real executable reaches hook, queue terminal state,
  receipt and canonical-effect verification; unavailable authentication stays
  an explicit bounded unverified result;
- writing a revision-bound evidence report without changing the parent
  W-07B acceptance gates.

## Scope

Allowed changes are limited to:

- `evals/runtime_benchmark.py` and its focused test/evidence helpers;
- `tests/test_w07b_process_recovery.py` and new test-only helpers;
- W-07B evidence plan/report and documentation indexes needed to bind the
  result.

No production file under `brain_eleven/runtime/` or any canonical authority
may change in this package. Hook definitions, live Claude/Codex settings,
live vault bytes, credentials, prompts, transcripts and memory content are
never written to or persisted by the harness.

## Invariants

- Temporary transcript roots are configured explicitly for both clients and
  are deleted after the run; no path or transcript text appears in evidence.
- The benchmark uses the existing launcher/worker/service contracts and must
  not weaken the three-second hook timeout or startup budget.
- A process crash leaves a retryable intent or receipt-reconciliation state;
  recovery produces exactly one terminal report and no canonical revision
  change.
- A report is accepted as evidence only when canonical verification is true;
  a queue `COMPLETED` row alone is insufficient.
- Native trust is `VERIFIED` only for an authenticated real executable in an
  isolated configuration. Host-level `claude auth status` or `codex login`
  output is a precondition, never proof. Missing auth/network is recorded as
  `BOUNDED_UNVERIFIED_*` and keeps W-07B `FIX-FIRST / NOT ACCEPTED`.
- Latency and dogfood rows are content-free and must not expose raw prompt,
  transcript, token, credential, exception or filesystem path data.
- Existing canonical MemoryStore, StateStore and ProjectRegistry bytes and
  revisions remain unchanged by failures and by the evidence harness.

## Required evidence

1. Deterministic reproduction showing the repaired synthetic benchmark reaches
   queue terminal states without a provenance-degraded false failure.
2. At least three repetitions for each worker/service crash boundary, with one
   report/receipt per intent and no stale staging residue.
3. The complete 2-client × 4-event × cold/warm latency table, with sample
   counts, p50, nearest-rank p95, timeout/budget status and exact head SHA.
4. Isolated authenticated native smoke for both clients when credentials and
   network are available; otherwise explicit bounded unverified rows and no
   acceptance claim.
5. Focused W-07B tests, full regression, critical flake8 (`E9,F63,F7,F82`),
   `compileall` and `git diff --check`.
6. Independent read-only review. Self-review cannot produce `SHIP`.

## Exit gate

W-07B-R1 may be marked **SHIP** only when the evidence is revision-bound,
privacy-safe, reproducible and independently reviewed. A repaired synthetic
benchmark or green process tests alone do not close native trust, latency or
dogfood gates. If any required cell or native client is unavailable, the
package remains **FIX-FIRST / NOT ACCEPTED** with the exact bounded failure
code preserved.

**Plan status: APPROVED — harness implementation extended at
`ca15e31eb5bf3ab987246b3f2b5ce8dd5bed06f3`; package remains FIX-FIRST / NOT
ACCEPTED pending authenticated native evidence, dogfood and independent review.**
