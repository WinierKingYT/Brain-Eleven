# Pre-Phase 20 — Core Intelligence Hardening Contract

**Status:** `PRE-08 VERIFIED / NEXT: PRE-09`

This is the controlled pre-Phase 20 program. It strengthens how
Brain-Eleven acquires, validates, represents, selects, and delivers memory.
It does **not** start a Knowledge Engine.

## Entry evidence

- Reviewed code SHA: `8f5513129d369525d3ffca1090cbd561323e0cfa`
- Validation: [GitHub Actions run #55](https://github.com/WinierKingYT/Brain-Eleven/actions/runs/33968422634)
  completed successfully, including Ubuntu/Windows unit tests, integration,
  coverage, public evaluation, Bandit, secret detection, dependency audit,
  Docker/Trivy, all Phase 15–19 evidence jobs, and the Foundation graduation
  job.
- The generated Foundation artifact correctly remained review-pending by
  design. The separate independent read-only Foundation review has now returned
  `SHIP`; see `CONTEXT-ENGINE-FOUNDATION-V1-INDEPENDENT-REVIEW.md`.
  `PRE-01` remains gated on the immutable Foundation tag for the final
  documentation revision. This program must not change Foundation authority
  contracts or promote V2 runtime paths before that tag exists.

## Scope and non-goals

Allowed work is bounded to capture reliability, evidence lineage, extraction
quality, memory/state truth, lifecycle correctness, retrieval precision,
context density, evaluation, privacy, and eventual production convergence.

Until this program graduates, it must not add a Phase 20 Knowledge Engine, a
cognitive controller, autonomous planning, outcome-learning weight updates,
or a second canonical memory authority.

## Authority laws

1. **Evidence is not memory.** Prompts, transcripts, tool output, Daily notes
   and manual requests are evidence. Canonical memory remains a validated
   interpretation.
2. **Model output never writes canonical storage by itself.** Any model-backed
   extractor may produce candidates only; deterministic validation and policy
   own acceptance.
3. **Memory, State, lifecycle mutation, and evidence are distinct.** Current
   operational facts prefer `StateStore`; durable rationale and lessons belong
   in `MemoryStore`; correction/resolution changes an existing lifecycle when
   its target is explicit.
4. **Existing Phase 14 MemoryStore semantics are protected.** Early evidence
   and temporal provenance use a separately revisioned provenance projection
   keyed by immutable `memory_id`. A MemoryStore schema migration requires its
   own backup, round-trip, rollback, and revision-evidence contract.
5. **Scope and safety precede ranking.** No prompt, model, usage signal, or
   similarity score can widen trusted scope, revive inactive data, or override
   canonical authority.

## Baseline inventory

| Area | Current entry point | Baseline finding |
|---|---|---|
| Session end | `.claude/hooks/session-end.sh` → `scripts/session_pipeline.py` | Runs compiler, validator, context compiler, and maintenance synchronously. |
| Prompt submit | `.claude/hooks/prompt-counter.sh` → `scripts/prompt-counter.py` | Counts/checkpoints prompts; it is not an evidence capture path. |
| Autonomous ingestion | `scripts/memory-compiler.py` | Daily-centric headings and regex/heuristics create candidates at capture time. |
| Canonical memory | `scripts/memory_store.py` | Revisioned, locked, atomic authority; frozen by Foundation policy. |
| Current truth | `scripts/state_store.py` | Separate revisioned, typed StateStore authority. |
| Shadow retrieval/context | `context_router/`, `authority/`, `context_compiler_v2/` | Read-only and shadow-only; no SessionStart promotion. |

The legacy Daily compiler remains a supported manual/legacy evidence adapter
throughout the migration. It is not the intended primary autonomous path once
the V2 capture pipeline graduates.

## Explicit rollout decisions

- **Raw evidence retention:** default `0` days. Raw prompt/transcript content
  may exist only in the protected queue while unprocessed and is removed after
  terminal processing. Long-lived records keep identity, source hash, locator,
  timing, project/session identity, and minimal provenance only.
- **Model-assisted extraction:** local opt-in only, with initial outputs sent
  to quarantine/review rather than automatic canonical commit. CI uses fixture
  providers and never needs a live network/model.
- **First production canary:** Brain-Eleven only, after all later promotion
  gates. The initial canary remains explicit and rollbackable.

## Package order

1. `PRE-00` — record this baseline and freeze the boundary.
2. `PRE-01` — define bounded hook-event identity and idempotency contracts.
3. `PRE-02` — add durable, at-least-once fast capture queue and content-safe
   ledger; remove expensive SessionEnd work from the fast path.
4. `PRE-03` — add typed evidence reader, role preservation, source hashing,
   retention, and the Daily adapter.
5. `PRE-04` through `PRE-07` — extraction, temporal/provenance, truth and
   lifecycle, and typed StateStore routing.
6. `PRE-08` through `PRE-10` — retrieval decision, diversity/coverage, and
   Compiler V2 promotion hardening.
7. `PRE-11` through `PRE-13` — private real-use evaluation, consolidation,
   canary, rollback, and single-pipeline graduation.

Every package must add deterministic tests and receive a separate read-only
review before the next package changes canonical behavior.

## PRE-01 — Capture event contract

PRE-01 is deliberately limited to parsing and identifying hook events. Its
versioned contract accepts only `SESSION_END` and `USER_PROMPT_SUBMIT` payloads
with a bounded session identity, project root and timezone-aware event time.
Session-end events require a transcript locator; prompt events retain only a
SHA-256 digest and length, never raw prompt text.

- Project identity is resolved read-only through `ProjectRegistry`; unknown
  projects remain `unresolved`, archived projects remain archived, and a
  corrupt registry raises an explicit error.
- Event and idempotency IDs are deterministic. Replaying the same session-end
  or prompt event produces the same identifiers; no queue or canonical effect
  exists in this package.
- The parser rejects malformed JSON, oversize input, unsupported fields and
  caller-supplied project-ID overrides. It does not open transcript paths,
  enqueue jobs, change hooks, or write MemoryStore/StateStore data.

## PRE-02 — Fast capture queue

PRE-02 replaces only the active hook hand-off. `SessionEnd` and
`UserPromptSubmit` now normalize bounded stdin through the PRE-01 contract and
append a local, idempotent job to `.brain-eleven/capture/`. The spool is
gitignored and contains `queued`, `processing`, `completed`, and
`dead-letter` states plus a content-safe JSONL ledger.

- The fast hooks do not read transcript files, call a model/network, compile
  Daily notes, run the legacy session pipeline, rebuild context, or write
  MemoryStore/StateStore data.
- Delivery is at-least-once: a deterministic job ID derives from the PRE-01
  idempotency key, so replaying an event acknowledges the existing job rather
  than creating another one. Queue state changes are lock-protected and use
  atomic local writes/renames; bounded retries and expired-lease recovery send
  exhausted jobs to dead letter.
- The queue may retain a transcript *locator* in its local job until a later
  worker processes it. It never writes raw prompt text. The ledger writes only
  IDs, hashes, project resolution, state, attempt counts and error codes.
- Queue backpressure, corrupt jobs, lock timeouts, and write failures are
  explicit errors. Hooks remain best-effort and return safely to Claude without
  echoing untrusted evidence.

`scripts/session_pipeline.py` and `scripts/prompt-counter.py` remain legacy
manual compatibility tools for now; neither is on the active PRE-02 hook path.
A transcript/evidence worker is explicitly deferred to PRE-03 and later.

Verification for the PRE-02 implementation commit `9397a026fee7c58bd33a8a9a1c504222baa350e0`:

- [Validation #59](https://github.com/WinierKingYT/Brain-Eleven/actions/runs/33971146711):
  success, including Ubuntu and Windows unit tests, integration, coverage,
  privacy, security, evaluation and Foundation-graduation regression gates.
- [Docker #59](https://github.com/WinierKingYT/Brain-Eleven/actions/runs/33971473714):
  success.

## PRE-03 — Evidence reader and retention boundary

PRE-03 adds `scripts/evidence.py`: a local evidence layer that reads bounded
JSONL transcripts with `user`, `assistant`, `tool`, and `system` role
attribution, plus a legacy/manual Daily.md adapter. It produces an in-memory
batch of raw source messages paired with `EvidenceRecord` metadata. Extraction
is expressly deferred: neither reader classifies claims nor writes memory,
state, lifecycle, graph, registry, or queue state.

- Persisted records live only under the ignored local capture tree and contain
  an evidence ID, source type, project/session identity, role, `captured_at`,
  optional `occurred_at` with precision, hashes, and a source locator. They do
  not serialize raw transcript/Daily/prompt text or full source paths.
- The default retention is zero days: `raw_retained=false` and no raw evidence
  file is created. Reprocessing the same source identity is idempotent.
- Transcript paths must be absolute regular local files, cannot be symlinks or
  parent-traversal paths, and are bounded by byte/message limits. Invalid UTF-8,
  malformed JSONL, changing files, missing files, and unsupported source shape
  return explicit errors rather than an empty-success result.
- Transcript message timestamps retain instant precision. A dated Daily entry
  retains only day precision; the implementation never invents an arbitrary
  time of day.

## PRE-04 — Deterministic extraction V2

PRE-04 adds `scripts/extraction.py`, a deterministic extraction provider over
the in-memory PRE-03 evidence batch. It preserves the evidence role boundary,
segments turns into propositions, classifies commitment language, and emits
either a project-scoped `NewMemoryCandidate`, a typed `StateMutationProposal`,
or a content-hash-only quarantine record.

- Assistant, tool, and system statements are proposals/observations, never
  user-backed decisions. Questions, hypotheticals, quoted prose, negations,
  low-evidence claims, secrets, and unresolved project identity are quarantined
  with stable reason codes.
- Current operational facts such as active failures and blocker resolution are
  routed to state proposals. Durable explicit decisions/lessons/preferences
  remain memory candidates. Explicit corrections produce a new candidate plus
  `LIFECYCLE_TARGET_UNKNOWN`; PRE-04 does not guess a prior memory ID or mutate
  lifecycle.
- Candidate content exists only in the in-memory extraction result for the
  later review/truth stage. Machine-safe serialization can omit content, and
  this package has no canonical write path, model/network dependency, or
  autonomous lifecycle mutation.

## PRE-05 — Canonical provenance and time projection

PRE-05 adds `scripts/memory_provenance.py`, a revision-bound derived
projection for temporal and evidence lineage. The Phase 14 canonical
MemoryStore remains unchanged and authoritative; migration preserves every
canonical memory ID and revision.

- Legacy `timestamp` values are conservatively mapped to `captured_at`.
  Daily source IDs may provide a day-precision `occurred_at`; no time of day
  is invented, and naive timestamps retain `unknown` precision.
- The projection records separate `occurred_at`, `captured_at`,
  `canonicalized_at`, `updated_at`, and `last_confirmed_at` slots, along with
  future evidence/session/job lineage fields. It contains metadata only and
  never copies memory content.
- Migration reads both validated and rejected canonical buckets, is
  revision-bound, idempotent, lock-protected, atomically written, and fails
  closed on corrupt projection or canonical input. Re-running against the
  same revision preserves the original projection timestamp.
- Runtime output is ignored under `.claude/memory-provenance.json`; the
  projection is derived state and is not a second memory authority.

Verification for the PRE-05 implementation commit `9c658456e4e13e2dd7a5040e3e665dc2b9a6b4ef`:

- [Validation #61](https://github.com/WinierKingYT/Brain-Eleven/actions/runs/33985606149):
  success, including Ubuntu and Windows unit tests, integration, coverage,
  privacy, security, evaluation and Foundation-graduation regression gates.
- [Docker #61](https://github.com/WinierKingYT/Brain-Eleven/actions/runs/33985969322):
  success.

## PRE-06 — Metadata-first memory truth and lifecycle

PRE-06 adds `scripts/memory_truth.py` as a typed truth boundary for
structured extraction candidates. It does not reinterpret free prose as
authority and it does not replace the existing MemoryStore or lifecycle
schema.

- Candidates are validated for commitment, scope, confidence, and secret
  safety before evaluation. Uncommitted, ambiguous, or missing-target input
  becomes `REVIEW_REQUIRED`; secrets are rejected.
- Exact scoped fingerprints produce `DUPLICATE` or explicit confirmation.
  Optional claim keys can expose an active conflict, but retrieval scores,
  text similarity, and missing provenance never create a winner.
- `SUPERSEDE_EXISTING` and `RESOLVE_EXISTING` require an explicit target,
  matching project scope, active lifecycle, and a checked successor. Cycles,
  cross-project targets, unknown lifecycle values, and inactive targets are
  not silently accepted.
- Commit mode uses the MemoryStore lock/reload/revision transaction. New
  memory commits are separately opt-in (`commit_new`), while dry-run truth
  evaluation is read-only. Corrupt canonical input is a hard failure, never
  empty success, and all result records contain IDs/revisions/reason codes
  rather than memory text.

Verification for the PRE-06 implementation commit `9fdc3293f435c78cf1bb96a1af3d90f84f833f8d`:

- [Validation #65](https://github.com/WinierKingYT/Brain-Eleven/actions/runs/33986830183):
  success, including Ubuntu and Windows unit tests, integration, coverage,
  privacy, security, evaluation and Foundation-graduation regression gates.
- [Docker #65](https://github.com/WinierKingYT/Brain-Eleven/actions/runs/33987238334):
  success.

## PRE-07 — State boundary integration

PRE-07 adds `scripts/state_boundary.py`, the only adapter between extraction
state proposals and the existing typed `StateService`. Current operational
facts are routed to canonical project state; durable decisions, lessons,
preferences, and open-loop memories remain outside this boundary for the
MemoryStore truth path.

- `ADD_BLOCKER`, `ADD_WORK_ITEM`, `SET_OBJECTIVE`, `SET_CURRENT_PHASE`, and
  `ADD_REQUIREMENT` use StateService typed mutations. Resolution operations
  require an explicit target ID; the boundary never guesses a lifecycle
  target from free text.
- Unknown or archived projects, missing state initialization, wrong-project
  proposals, invalid transitions, stale revisions, corrupt state, and invalid
  provenance fail closed with stable status/reason codes. No project is
  auto-registered.
- Only `COMMITTED` and `OBSERVED` proposals with trusted `user`, `system`, or
  `tool` provenance can be committed. AI-proposed, ambiguous, or missing
  provenance remains review-only. Dry-run and classification paths perform no
  canonical write.
- State routing never writes MemoryStore. Batch routing carries the latest
  per-project revision forward and rejects proposals for other projects.
- Extraction now recognizes requirement proposals and treats explicit
  resolved operational facts as observations, while preserving the existing
  safety quarantine behavior for proposals, hypotheticals, questions, quotes,
  and secrets.

Verification for the PRE-07 implementation commit `964602c74976f148140bb82ddd23c886061ed31b` and fix commits:

- Bundled Python `compileall` passed for `scripts/` and `tests/`.
- Focused PRE-07 smoke passed: blocker-to-state commit, memory candidate
  skip, provenance/target rejection, and revision advancement.
- Boundary tests cover classification, dry-run, all typed operations,
  lifecycle resolution, invalid transitions, archived/unknown projects,
  batch isolation, and MemoryStore immutability.
- [Validation #70](https://github.com/WinierKingYT/Brain-Eleven/actions/runs/33988579152):
  success on Ubuntu and Windows, including unit, integration, coverage,
  privacy, security, evaluation, router, authority, compiler, and Foundation
  graduation gates.
- The bundled local runtime does not include `pytest`; full test verification
  is recorded from the green remote validation workflow above.

## PRE-08 — Task-need retrieval decision engine

PRE-08 adds the read-only `retrieval_decision_v2` package. It consumes the
content-free Router and metadata-first Authority contracts and produces a
deterministic, content-free selection decision. It does not retrieve new
memory, widen Router scope, change authority, write canonical memory/state,
or alter the active ContextCompiler/SessionStart path.

- Needs are derived deterministically from task intent, explicit/inherited
  constraints, context hints, and active state blockers. Need matching is a
  ranking hint only; it cannot override scope, lifecycle, revision, or
  authority policy.
- `CURRENT_PROJECT`, `GLOBAL_ONLY`, and `SELECTED_PROJECTS` remain bounded by
  the Router plan. Prompt text cannot widen them, selected projects are not
  compared against one another, and global records are admitted only by the
  trusted Router scope.
- Active lifecycle and source-revision filters run before scoring. History is
  opt-in, superseded/historical/inapplicable/invalid authority outcomes are
  excluded, duplicate candidates/fingerprint groups are reduced
  deterministically, and selection budget omissions are explicit.
- Output contains only IDs, canonical references, source metadata, need and
  channel signals, scores, omission reasons, revisions, and safe telemetry;
  memory text is never serialized.
- Coverage and Bandit gates now include `retrieval_decision_v2`, and the
  contract suite covers invalid inputs, scope isolation, lifecycle/history,
  revision races, authority mismatches, duplicate reduction, budget bounds,
  and content-free output.

Implementation commits:

- `d4227888240b461adeaa6fd53ada4812425c5711` — retrieval decision engine.
- `a899c247ac8b77028d98bcc4badb8b51094c3c58` — package coverage/security
  gate hardening and boundary tests.
- `b0ad09ba1ef97b8e2b96e942ec4d1dc5b1aba812` — coverage fixture update.

Verification for PRE-08:

- Local bundled Python compile and focused contract smoke passed (10 tests).
- [Validation #74](https://github.com/WinierKingYT/Brain-Eleven/actions/runs/33989942218):
  success on Ubuntu and Windows, including the real retrieval package
  coverage group, integration, privacy, security, evaluation, Router,
  Authority, Compiler, and Foundation-graduation gates.
- Validation #73 is retained as a historical failed run from before the
  coverage fixture correction; it is not used as PRE-08 evidence.

## PRE-00 completion criteria

- The Foundation candidate SHA, CI run, and derived evidence are recorded.
- Current hook and ingestion entry points are inventoried without altering
  their behavior.
- Phase 14–19 contracts remain unmodified.
- Retention, extraction rollout, and canary decisions are explicit.
- `PRE-01` cannot begin until the independent Foundation review is `SHIP` and
  the immutable frozen SHA/tag has been recorded.
