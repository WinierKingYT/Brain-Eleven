# IG-04 B2 Package Report

**PACKAGE:** IG-04 B2 — Review Deduplication and Deterministic Ordering
**REVISION:** `c08f64e057c8ae53047fc80e0aa3788813be1fd6`

## OBJECTIVE

Deduplicate pending review candidates by project-scoped content fingerprint,
retain duplicate records and evidence references, finalize the group through a
single visible decision, and return a fixed review order without model or
embedding signals. B1 acceptance/rejection/expiry, canonical writes,
authentication, scope isolation and V2 remain unchanged.

## FILES CHANGED

* `brain_eleven/runtime/review.py` — content fingerprint groups, deterministic
  sort key, duplicate links, hidden duplicate presentation and grouped terminal
  finalization.
* `brain_eleven/runtime/service.py` — direct duplicate IDs resolve to the
  deterministic primary before acceptance.
* `brain_eleven/runtime/worker.py` — receipt verification accepts the terminal
  review records produced by grouped finalization.
* `tests/test_ig04_b2_review_order.py` — deduplication, evidence retention,
  grouped acceptance, fixed ordering and project isolation.

## ROOT CAUSES ADDRESSED

* Multiple captures of the same project-scoped content could appear as separate
  pending review cards.
* A duplicate capture could be accepted through a stale/direct ID and create a
  second canonical effect.
* Review ordering previously followed filesystem enumeration rather than an
  explicit stable policy.
* Terminalizing one duplicate could invalidate another job's receipt replay.

## TESTS ADDED

1. Same project/content with different evidence is stored twice, one pending
   item is visible, the other is linked as `duplicate_of`, both evidence lists
   remain, and one accept creates one canonical memory.
2. Pending review order is confidence descending, created time ascending (oldest
   first), candidate type order `STATE_MUTATION`, `NEW_MEMORY`, then unknown,
   followed by review ID; repeated listing returns the same order.
3. Identical content in different projects is never grouped.

## TESTS EXECUTED

* `.venv\\Scripts\\python.exe -m pytest tests/test_ig04_b2_review_order.py tests/test_ig04_b1_human_approval.py -q` — **6 passed**.
* `.venv\\Scripts\\python.exe -m pytest tests -q` — **854 passed, 2 warnings**.
* Critical flake8 (`E9,F63,F7,F82`) on changed runtime files — **pass**.
* `compileall` for `brain_eleven` — **pass**.
* `git diff --check` — **pass**.

## QUALITY METRICS BEFORE / AFTER

Review presentation is now deterministic and duplicate noise is reduced at the
pending-review surface. No retrieval precision/recall claim is made and no
ranking, embedding or V2 quality metric was tuned.

## SAFETY METRICS

Grouping keys include project scope and content semantics; projects cannot be
grouped together. Duplicate records retain evidence references but remain
`PENDING` and non-canonical until the primary decision. Group acceptance uses
one primary operation identity. Terminal review receipt verification accepts
the bounded terminal audit record without treating it as a new canonical
effect.

## KNOWN LIMITATIONS

The B2 feature has not been independently reviewed or promoted as a
graduation package. Remote exact-head CI evidence is also not recorded in this
package report.

## OPEN FAILURES

* Independent read-only review is pending; implementer self-review is not
  accepted evidence.
* Exact-head remote CI evidence is not recorded in this package report.

## INDEPENDENT REVIEW

**PENDING — user-owned review.** No `SHIP` verdict is issued here.

## SCORE BEFORE / AFTER

No graduation score change. The package improves review noise and ordering
determinism only; B1 and intelligence quality baselines remain unchanged.

## VERDICT

**FIX-FIRST / NOT ACCEPTED** — implementation and local regression evidence are
complete, but the contract-required independent review remains open.
