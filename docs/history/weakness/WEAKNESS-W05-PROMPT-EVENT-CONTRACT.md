# W-05 — Prompt Event Terminal Semantics Contract

**Status:** BOUNDED CONTRACT / IMPLEMENTATION PENDING  
**Program:** Engineering Weak-Point Improvement Goal  
**Phase 20:** FROZEN / LOCKED  
**V2:** SHADOW

## Objective

Make `USER_PROMPT_SUBMIT` queue events terminal and content-safe. These events
carry only a prompt digest/length, not evidence text or a transcript locator;
they must not enter the SessionEnd evidence retry/dead-letter loop.

## Current failure

`Worker.process()` returns `NO_EVIDENCE` whenever a queued event has no
`transcript_path`. `Worker.once()` converts every non-`PROCESSED` result into a
retry, so a prompt event consumes attempts and can become an unexplained dead
letter despite having no readable evidence by design.

## Bounded implementation

1. Detect `USER_PROMPT_SUBMIT` by its validated event type before the transcript
   branch. Return a normal `PROCESSED` result with zero messages, evidence,
   canonical effects and review effects, `effect_verified=True`, an immutable
   empty cursor and a checkpoint key bound to the event identity.
2. Update checkpoint identity resolution so events without a transcript use a
   content-free event locator (`event_id`), while SessionEnd keeps its existing
   transcript locator binding.
3. Let the existing receipt writer, replay verifier, queue commit and ledger
   prove terminal completion. No new queue status, canonical write, prompt
   content storage or retry policy is introduced.
4. Keep SessionEnd/no-locator and provenance failures on their existing
   retry/degraded paths; this package changes only the explicitly validated
   prompt event type.

## Invariants

- Raw prompt text is never accepted from this path or persisted; only the
  existing digest/length envelope remains.
- Prompt event completion produces no MemoryStore, StateStore, graph, review or
  evidence effect.
- One receipt and one completed queue job are produced; replay is idempotent.
- Receipt cursor/checkpoint identity cannot be confused with a transcript job.
- Project scope and queue locking remain unchanged.

## Acceptance criteria

- A validated prompt event reaches `COMMITTED` on its first worker attempt with
  a verified zero-effect receipt.
- Replaying the completed event does not create another effect or retry.
- Its ledger/receipt contain no raw prompt or transcript path.
- A SessionEnd missing/late transcript still follows W-04 behavior.
- Existing capture queue/worker/evidence suites pass; focused prompt tests cover
  direct queue delivery, receipt, replay and canonical-store invariants.
- Critical flake8, compile/import sanity, full regression and
  `git diff --check` pass.
- Independent read-only review returns exactly `SHIP`, `FIX-FIRST` or
  `RETHINK`.

**Package verdict:** REVIEW PENDING until implementation and independent review.
