# Pre-Phase 20 — Core Intelligence Hardening Contract

**Status:** `PRE-02 VERIFIED / PRE-03 READY`

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

## PRE-00 completion criteria

- The Foundation candidate SHA, CI run, and derived evidence are recorded.
- Current hook and ingestion entry points are inventoried without altering
  their behavior.
- Phase 14–19 contracts remain unmodified.
- Retention, extraction rollout, and canary decisions are explicit.
- `PRE-01` cannot begin until the independent Foundation review is `SHIP` and
  the immutable frozen SHA/tag has been recorded.
