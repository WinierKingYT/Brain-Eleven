# EXTRACT-01 — Review Queue Noise Reduction

**Status:** IMPLEMENTED / LOCAL VERIFICATION COMPLETE

**Date:** 2026-09-24

**Scope:** deterministic extraction and worker review admission only

## Evidence and problem

The deterministic extractor already quarantined user questions,
hypotheticals, quoted material, negated claims and uncertain statements.
However, when an input produced no deterministic candidate, the runtime worker
split the same user text again and inserted every segment into `ReviewStore` as
`LOW_EVIDENCE_COMMITMENT`. This did not bypass canonical approval, but it
reintroduced filtered material into the human review queue.

A content-free count of the live local review metadata before implementation
showed:

- 2,412 total review records; 2,398 pending.
- 2,186 records (`90.6%`) had reason `LOW_EVIDENCE_COMMITMENT`.
- Those records contained 515 quoted, 1,531 uncertain, 78 question, 27
  hypothetical and 25 negated commitments.
- 2,176 of the 2,186 were typed only as generic observations.
- Five explicit preferences were present, so removing all uncertain material
  without improving classification would lose a small legitimate category.

No review content was printed or copied for this measurement; only bounded
status, reason, commitment and type counters were read.

## Contract

1. Content quarantined as question, hypothetical, quote, negation or generic
   uncertainty must not be inserted into `ReviewStore` by a fallback path.
2. Explicit user decisions, current facts, requirements, preferences and
   lessons remain eligible for the existing review/canonical policy.
3. Assistant/model proposals remain governed by their existing explicit model
   and semantic review paths.
4. Existing pending review records are not deleted, rewritten or accepted.
5. Canonical memory/state, rollout mode, thresholds, corpora, retrieval and V2
   behavior remain unchanged.
6. The change must preserve wrong-project, provenance, human-approval,
   duplicate and supersession protections.

## Implementation

- `scripts/extraction.py` classifies explicit user preferences and lessons as
  `OBSERVED`, preserving them as deterministic candidates.
- `brain_eleven/runtime/worker.py` removes the fallback that recreated every
  candidate-free user segment as a low-evidence review item.
- `tests/test_extract01_review_noise.py` covers the five filtered categories,
  retained preference/lesson behavior and the complete worker-to-review path.

## Verification

- TDD RED: preference/lesson preservation and worker review suppression failed
  before implementation (3 failures, 5 passes).
- GREEN: focused EXTRACT-01 and extraction suite: 16 passed.
- Extraction, semantic provider, IG-04 B1/B2, shadow acceptance, PRE-13 runtime
  and MEMCLAIM-01 regression package: 139 passed.
- Expanded capture closure, provenance, terminal-state, memory-truth and review
  integrity regression package: 255 passed.
- Clean committed-tree full suite: 1,608 passed, 4 skipped.

## Expected effect and limitation

For the measured historical distribution, this rule would have prevented the
2,186 low-evidence fallback records while retaining explicit preferences and
lessons through deterministic classification. This is a retrospective shape
estimate, not a claim that the existing queue was modified or that future
precision is already measured.

The current 2,398 pending records remain untouched. Backlog cleanup requires a
separate explicit, reversible policy; EXTRACT-01 changes only future admission.
