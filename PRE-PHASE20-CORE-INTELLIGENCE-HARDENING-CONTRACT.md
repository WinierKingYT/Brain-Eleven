# Pre-Phase 20 — Core Intelligence Hardening Contract

**Status:** `PRE-00 BASELINE RECORDED / FOUNDATION REVIEW PENDING`

This is the controlled pre-Phase 20 program. It strengthens how
Brain-Eleven acquires, validates, represents, selects, and delivers memory.
It does **not** start a Knowledge Engine.

## Entry evidence

- Candidate SHA: `e5c1069571e966d7b96b564413fb85be3055ca6c`
- Validation: [GitHub Actions run #52](https://github.com/WinierKingYT/Brain-Eleven/actions/runs/33896562025)
  completed successfully, including Ubuntu/Windows unit tests, integration,
  coverage, public evaluation, Bandit, secret detection, dependency audit,
  Docker/Trivy, all Phase 15–19 evidence jobs, and the Foundation graduation
  job.
- The generated Foundation artifact remains review-pending by design. This
  program may record its baseline but must not call the Foundation frozen,
  change its authority contracts, or promote V2 runtime paths until the
  separate independent read-only review has returned `SHIP`.

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

## PRE-00 completion criteria

- The Foundation candidate SHA, CI run, and derived evidence are recorded.
- Current hook and ingestion entry points are inventoried without altering
  their behavior.
- Phase 14–19 contracts remain unmodified.
- Retention, extraction rollout, and canary decisions are explicit.
- `PRE-01` cannot begin until the independent Foundation review is `SHIP` and
  the frozen SHA/tag has been recorded.
