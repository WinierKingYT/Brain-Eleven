# IG-04 B2 Independent Acceptance Review

**REVIEWED REPOSITORY:** `WinierKingYT/Brain-Eleven`
**REVIEWED BRANCH:** `master`
**REVIEWED HEAD:** `80f36507706b341bcb0eb441436c38dd8c58fbae`
**IMPLEMENTATION REVISION:** `cd59da42dca3b2ae41507a9530479f37dc3be5fb`
**REVIEW DATE:** 2026-09-10
**REVIEWER:** Claude session `brain-eleven-66`
**REVIEWER ROLE:** Independent read-only reviewer
**IMPLEMENTATION PARTICIPATION:** None — B2 was implemented by Codex; this
review neither wrote nor edited `brain_eleven/runtime/*` or the B2 tests.
**MUTATIONS PERFORMED:** None to reviewed code. (This document itself.)

## Method

Independently re-run on this exact HEAD, not read-and-trusted:

- `python -m pytest tests/test_ig04_b1_human_approval.py tests/test_ig04_b2_review_order.py -v`
- `python -m pytest tests -m "not integration and not graduation" -q`
- Read `brain_eleven/runtime/review.py`'s `_sort_key`, duplicate-grouping and
  `list()` logic line by line, and `service.py`'s accept-path change for
  duplicate-ID resolution.
- Read the full B2 test file and checked each assertion against an actual
  contract acceptance criterion, not the package report's description of one.

## Contract Findings (against `IG04-B2-CONTRACT.md`'s 6 acceptance criteria)

| # | Criterion | Finding |
|---|---|---|
| 1 | Dedup correctness: same project+fingerprint collapses to one visible item; accept/reject resolves both; a materially different third candidate stays separate | **Verified.** `test_b2_hides_pending_duplicates_and_finalizes_the_group_once` shows two same-content candidates (different confidence) collapse to one visible item, the hidden one carries `duplicate_of`, both `evidence_refs` survive into their respective terminal records, and a single accept produces exactly one canonical memory while both terminal records read `ACCEPTED`. |
| 2 | Ordering deterministic and tested | **Verified.** `test_b2_review_order_is_fixed_by_confidence_age_type_and_id` asserts an exact order for a fixed 4-candidate set (confidence desc → age asc → type rank → id) and calls `list()` twice to confirm repeat-stability. Code review confirms one `_sort_key` function drives both which duplicate becomes the visible "primary" and the final list order — the same rule everywhere, not two divergent policies. |
| 3 | No regression to B1 | **Verified, independently re-run.** All 3 B1 tests plus 4 B2 tests pass together (7/7) on this HEAD in this (Linux) environment. |
| 4 | No new leakage surface across projects | **Verified.** `test_b2_content_groups_are_project_scoped` shows identical content in two different projects is never grouped — both remain independently visible. |
| 5 | Regression | **Verified, independently re-run.** `806 passed, 49 deselected` on the fast suite — matches the implementer's `855` once the same 49 integration/graduation-marked tests are added back (`855 = 806 + 49`), so the counts reconcile rather than merely both being green. |
| 6 | Independent review returns SHIP | This document. |

## Additional Finding Beyond the Six Criteria

The contract didn't specify which candidate becomes the visible "primary"
when duplicates differ in confidence. The implementation picks the one the
same `_sort_key` would rank first (here: higher confidence) — a reasonable,
and importantly *consistent*, choice: the representative shown is always the
one the ordering itself would prefer, not an arbitrary "first written" pick.
Worth noting explicitly in case a future package assumes "first captured" was
the rule.

## Deferred / Not Verified — UPDATED 2026-09-10

Remote CI was checked directly via the GitHub Actions API after this review:
it had actually been running and failing on every push (unrelated
pre-existing regression, fixed at `647bfad`), not "not run" as originally
stated here. Confirmed green on the exact-head commit chain covering B2
(only the long-standing, already-documented PRE-13 quality gate remains
red, unrelated to B1/B2). See `IG04-B1-INDEPENDENT-REVIEW.md` for the full
finding.

- **Live native-client trust** — out of scope for B2 specifically (it's a
  B1-level, already-tracked item); not re-verified here.

## P0 Findings

None.

## P1 Findings

None.

## P2 Findings

None beyond the note above.

## Final Verdict

**SHIP** — bounded to the IG-04 B2 implementation reviewed on
`cd59da42dca3b2ae41507a9530479f37dc3be5fb`.

This closes B2's independent-review acceptance criterion. It does not verify
remote CI (open, tracked with B1's same follow-up), does not promote V2, and
does not open Phase 20 or reopen IG-04's deferred original scope.
