# W-05 Package Report — Prompt Event Terminal Semantics

**PACKAGE:** W-05 / prompt event terminal semantics
**REVISION:** 1f98a7d
**OBJECTIVE:** Prevent digest-only `USER_PROMPT_SUBMIT` queue events from
entering the transcript evidence retry/dead-letter loop.

## Files changed

- `brain_eleven/runtime/worker.py` — validated prompt events now produce a
  zero-effect processed result; checkpoint identity supports events without a
  transcript locator.
- `tests/test_w05_prompt_event.py` — terminal receipt, zero-effect, no-raw-
  prompt and post-receipt ack replay coverage.

## Root cause addressed

Prompt events intentionally carry only a digest/length envelope. The worker
previously returned `NO_EVIDENCE`, and `Worker.once()` converted that result to
retry/dead-letter even though no transcript could ever be read from the event.

## Behavior and safety

- Only the validated `USER_PROMPT_SUBMIT` event type takes the terminal no-op
  path.
- Receipt has zero evidence, canonical and review effects and an empty cursor;
  existing receipt verification, queue commit and replay handling remain in
  control.
- SessionEnd and provenance failure behavior is unchanged.
- No raw prompt text, transcript locator or canonical store effect is added.

## Tests executed

- W-05 + affected capture/runtime suite: **110 passed, 2 warnings**.
- Full suite: **973 passed, 2 warnings**.
- Critical flake8 (`E9,F63,F7,F82`): **PASS**.
- `compileall`: **PASS**.
- `git diff --check`: **PASS**.

## Quality metrics

**BEFORE:** Digest-only prompt events consumed retry attempts and could become
unexplained dead letters; full suite was 971 passed after W-04.
**AFTER:** Prompt events complete once with a verified zero-effect receipt and
replay safely; full suite is 973 passed.
**Capture score:** 8.5 → 8.5 provisional.

## Known limitations / deferred work

This package does not capture prompt content, infer a transcript locator,
change SessionStart/UserPromptSubmit context delivery, or alter extraction,
retrieval, V2 or Phase 20 behavior.

## Independent review

Required and pending. The reviewer must inspect exact revision, contract,
receipt identity, no-effect behavior, regression evidence and deferred
boundaries, then return exactly `SHIP`, `FIX-FIRST` or `RETHINK`.

**VERDICT:** REVIEW PENDING
