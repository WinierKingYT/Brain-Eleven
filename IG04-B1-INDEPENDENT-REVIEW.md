# IG-04 B1 Independent Acceptance Review

**REVIEWED REPOSITORY:** `WinierKingYT/Brain-Eleven`
**REVIEWED BRANCH:** `master`
**REVIEWED HEAD:** `2b8373ee53c5fce3c11681b4f86fbac4ab9a9624`
**IMPLEMENTATION REVISION:** `4edd4dfdf399f1670479091d261fe1390d338e0e`
**REVIEW DATE:** 2026-09-10
**REVIEWER:** Claude session `brain-eleven-f1`
**REVIEWER ROLE:** Independent read-only reviewer
**IMPLEMENTATION PARTICIPATION:** None — B1 was implemented by Codex; this
review neither wrote nor edited `brain_eleven/runtime/*` or the B1 tests.
**MUTATIONS PERFORMED:** None to reviewed code. (This document itself.)

## Method

Package-report claims were **not** taken on trust. Independently re-run on
this exact HEAD, in a different environment (Linux) than the implementer's
evidence (Windows `.venv`):

- `python -m pytest tests/test_ig04_b1_human_approval.py -v`
- `python -m pytest tests -m "not integration and not graduation" -q`
- Read `brain_eleven/runtime/review.py` and the `review_action` accept path in
  `brain_eleven/runtime/service.py` line by line.
- Read the full B1 test file to check each acceptance-criterion claim against
  an actual assertion, not a description.

## Contract Findings (against `IG04-B1-CONTRACT.md`'s 8 acceptance criteria)

| # | Criterion | Finding |
|---|---|---|
| 1 | Eligibility: pending/rejected never in V1 hook output | **Verified structurally, not just by filter.** `ReviewStore` is a separate store from `MemoryStore`; a candidate only enters `MemoryStore` (and thus becomes retrievable) on `ACCEPTED`. Test directly asserts `compile_context(...)` excludes the candidate's content pre-accept and includes it post-accept. |
| 2 | User action: review API lists scoped pending items; accept produces exactly one canonical effect | **Verified.** `/api/review/candidates` test confirms scoped listing; accept test confirms exactly one `validated_memory` entry, and a repeated accept does not create a second one. |
| 3 | Rejection: terminal, replay does not re-propose | **Verified.** Rejecting, then re-adding the same project/content/evidence fingerprint under a different candidate ID, returns the same terminal record and status stays `REJECTED`. |
| 4 | Crash/replay safety (pre/post-write accept, duplicate delivery, worker restart, CAS conflict) | **Partially verified.** Code review shows the durable pattern needed for this: `accept_intent` is written to the review record *before* the canonical write (`service.py:47-51`), a deterministic `op_id` derived from `review_id` is used for the canonical write, and `expected_revision` is threaded through as a CAS guard. This is the same pattern the Foundation's already-graduated concurrent-writer/crash-recovery suite covers for `MemoryStore` generally. However, **no new B1-specific test kills the process between intent-write and canonical-write**, or forces a CAS conflict on accept. The mechanism is sound by inspection and inherited coverage; a dedicated B1 crash-injection test is still missing. |
| 5 | Safety: leakage, secret content absent from review telemetry | **Verified for what's tested.** Terminal review records drop `candidate` entirely (`"candidate" not in rejected`) and the content string is confirmed absent (`"SQLite" not in json.dumps(rejected)`). Cross-project leakage is not given a new B1-specific test, but candidates carry `project_id` and rely on the already-graduated project-isolation boundary once they reach `MemoryStore`. |
| 6 | Runtime: SessionStart stays non-interactive; single-switch rollback | **Verified.** `b1_human_approval` defaults `False`, is explicitly toggleable, and nothing in the reviewed diff makes `compile_context` or the hooks block on user input. |
| 7 | Regression: existing suites green + focused E2E (capture→review→accept/reject→retrieval) | **Verified, independently re-run.** `802 passed, 0 failed` on this HEAD, in a different environment than the implementer's. `test_b1_capture_requires_review_and_acceptance_is_one_canonical_effect` is a genuine, single-test walk of the full chain: enqueue → worker → PENDING → API list → excluded from context → accept → included in context → replay-safe. |
| 8 | Independent review returns SHIP | This document. |

## Baseline-v3 Fix (adjacent to B1, same head)

Also independently re-verified: `tests/test_evaluation_baseline_snapshot.py`
now passes on this HEAD in this (Linux) environment, where it previously
failed with a float-precision mismatch (`0.1799999999999996` vs
`0.18000000000000002`) that was environment-independent, not a fingerprint
staleness issue. Confirmed fixed, not just claimed fixed.

## Human Checkpoint Finding

The contract requires Ahmet's explicit approval **before** implementation
began. This review cannot independently verify the timing or content of that
approval from repository state alone — it is not a repo-observable fact.
Ahmet has confirmed verbally in this session that the approval occurred
before implementation started. This review records that confirmation; it is
not itself evidence of it.

## Deferred / Not Verified

- **Remote exact-head CI.** Not run by this reviewer; no CI access in this
  session. Package report marks this open — unchanged.
- **Native Claude/Codex client trust.** Not verified — no live authenticated
  client turn was exercised. Package report marks this open — unchanged.
- **Cross-project leakage for B1 candidates specifically** — inherited from
  already-graduated `MemoryStore` isolation, not covered by a new B1 test.
- **Worker-restart / CAS-conflict on the accept path specifically** — sound
  by code inspection and inherited pattern, not covered by a new B1 test.

## P0 Findings

None.

## P1 Findings

None.

## P2 Findings — RESOLVED 2026-09-10

Both closed at `d97e666` (`tests/test_ig04_b1_p2_coverage.py`), independently
verified: read the 3 new tests line by line (real fault-injection via
monkeypatch, a genuine CAS conflict via a competing canonical write, and a
two-real-project fingerprint/visibility check — not happy-path repeats), and
independently re-ran them (6/6 passed) plus the full suite (858 passed, 0
failed on this reviewer's Linux environment). The implementer separately
reported one "IG-00 cold native" failure in their full-suite run on Windows
that passed in isolation; this reviewer's full run reproduced no failure at
all. Treated as environment-specific, not a regression from this change, but
worth re-checking if it recurs.

- ~~Add a focused B1 test that kills/interrupts between `accept_intent` write
  and the canonical write, and one that forces a stale `expected_revision` on
  accept~~ — done.
- ~~Add a B1-specific cross-project rejection/acceptance test~~ — done.

## Final Verdict

**SHIP** — bounded to the IG-04 B1 implementation reviewed on
`4edd4dfdf399f1670479091d261fe1390d338e0e`.

This closes B1's independent-review acceptance criterion. It does not verify
remote CI or live native-client trust (both remain open per the package
report), does not promote V2, and does not open Phase 20. The two P2 items
are recommended follow-up tests, not blockers to this verdict — the
underlying safety property they'd cover is already provided by
already-graduated Foundation-level guarantees, just not by a B1-specific
regression test yet.
