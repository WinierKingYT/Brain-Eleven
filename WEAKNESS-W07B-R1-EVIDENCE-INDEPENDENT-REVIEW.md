# W-07B R1 Evidence Harness — Independent Review

**REVIEWER:** independent read-only reviewer (`/root/w10_exact_review`)

**CODE REVISION:** `c17fd84ac95742088c60fc4ec250dbd26db37fd7`

**DOCUMENTATION HEAD:** `ee72d94342e811089e836d7cb1912c5ec86c2831`

**VERDICT:** FIX-FIRST

## REVIEW SCOPE

The reviewer inspected the R1 contract, `evals/runtime_benchmark.py`, focused
tests, exact revision metadata, privacy/scope boundaries and the committed
full-suite evidence. No files were modified by the reviewer.

## VERIFIED

- Both hook `TimeoutExpired` paths record bounded `TIMEOUT` status, preserve
  elapsed timing and continue to a visible report; cleanup failures are also
  bounded.
- The synthetic harness is evidence-only and isolated: disposable vault and
  transcript roots, 20/20 canonical effects, revision/count validation, no
  dead letters, and no live/HOLDOUT mutation.
- Report, `PROJECT-STATUS.md`, `NEXT.md`, `DOCUMENTATION-AUTHORITY.md` and
  the contract bind the same implementation revision; focused evidence is
  37/37 and committed full regression is 1342 passed, 4 skipped, 2 warnings.
- Contract scope and privacy rules remain bounded; no production or canonical
  authority implementation was changed.

## OPEN GATES

- Authenticated isolated native Claude trust is unverified.
- Authenticated isolated native Codex trust is unverified.
- The complete 2-client × 4-event × cold/warm latency matrix is absent.
- Privacy-safe multi-session dogfood evidence is absent.

These are acceptance requirements from the parent W-07B contract, not defects
that can be relabeled as passed by the synthetic harness. W-07B therefore
remains `FIX-FIRST / NOT ACCEPTED`; V2 remains `SHADOW` and Phase 20 remains
`FROZEN / LOCKED`.

**Independent review status: recorded; package acceptance is not granted.**
