# IG01-F V2 Regression Investigation — Evidence Report

**Status:** COMPLETE — closes
`docs/contracts/IG01F-V2-REGRESSION-INVESTIGATION-CONTRACT.md`.
**Result:** Hypothesis tested and refuted. A different, evidence-backed
finding replaces it. Classified **structural**, not a narrow fixable bug —
per the contract's own terms, this is a valid, complete result.
**Does not authorize any V2 change, promotion, or new package.** Any
follow-up is a separate, explicitly authorized package per
`docs/programs/WORK-INTAKE-RULE.md`.

## What was tested

Issue [#2](https://github.com/WinierKingYT/Brain-Eleven/issues/2) and the
approved contract asked: why does V2 underperform both V1 and a query-blind
recency baseline on `ig01f-recency-v1` (branch `ig/ig01f-naive-baseline`,
frozen, DEV+VALIDATION only, no HOLDOUT read)?

**First hypothesis (this session's initial read of the code):**
`evals/compiler_v2_provider.py`'s `CompilerV2ContextProvider` calls
`ContextCompilerV2(vault).compile(CompilationRequest(...))` **without**
`selection=`, which skips `RetrievalDecisionEngine` and
`ContextDensityEngine` entirely — the same two selection stages that
`brain_eleven/runtime/context.py`'s real `compile_task` wires before
`ContextCompilerV2.compile()`. In `context_compiler_v2/planner.py`'s
`choose()`, an absent `selection_order` degenerates the optional-candidate
sort key to tier → status → alphabetical candidate ID, ignoring the query
completely. This looked like a plausible, narrow, single-file defect: wire
in the missing stage, V2 should improve.

**Test:** built `evals/ig01f-investigation/compare_v2_probe.py`, a
read-only A/B probe. It reuses `CompilerV2ContextProvider` unchanged as
"existing," and adds `CorrectedV2Provider`, which runs the exact same
`ContextRouter → AuthorityResolver → CompilerEvidenceAdapter` steps, then
additionally wires `RetrievalDecisionEngine().select(...)` and
`ContextDensityEngine().select(...)` before calling
`ContextCompilerV2.compile(..., selection=density)` — matching
`compile_task`'s real wiring exactly. Both providers were run against all
114 DEV+VALIDATION cases (no HOLDOUT), scored with the frozen
`evals.ig01c.metrics.evaluate_retrieval_case`, no threshold or corpus
changes.

**Result: the hypothesis is false.** Wiring in the "correct" selection
stage makes V2 **worse**, not better.

| | existing (bare, current prod behavior) | corrected (selection wired, matches `compile_task`) |
|---|---|---|
| n | 114 | 114 |
| aggregate macro F1 | 0.11442786069651743 | 0.05970149253731343 |

Paired per-case comparison (`raw_comparison.json`, 67 cases with a
comparable F1 on both sides, 47 not-applicable on at least one side):

| | count |
|---|---|
| existing (bare) wins on F1 | **11** |
| corrected (selection-wired) wins on F1 | **0** |
| ties | 56 |
| of the 11 existing wins, corrected's selection was **empty** | **11 / 11** |

Every single case where the two providers diverge, the "corrected"
(selection-wired) provider returns nothing at all. It never wins a case.

## Root-cause case

`ig-eval-v2-explicit_decision-en-2`, prompt: *"Our decision is to use
SQLite."* — `required_ids = ["mem-ig01f-1228824e693370d3982a"]`.

- **existing (bare):** `retrieved_ids = ["mem-ig01f-1228824e693370d3982a", "mem-ig01f-7c79126718a104654ff0"]`
  — found the required memory. `f1 = 0.333`, `mandatory_recall = 1.0`,
  `mrr = 1.0`.
- **corrected (selection-wired):** `retrieved_ids = []` — found nothing.
  `f1 = 0.0`, `mandatory_recall = 0.0`, `empty_selection: true`.

Tracing the corrected path: `CompilerEvidenceAdapter.snapshot()` produces
the same candidate set for both providers (confirmed — the two providers
share every step up to this point). The divergence happens inside
`RetrievalDecisionEngine().select(...)`
(`retrieval_decision_v2/engine.py`): its lexical/term-overlap relevance
filter (`INSUFFICIENT_TASK_RELEVANCE`) excludes
`mem-ig01f-1228824e693370d3982a` from `decision.selected` before it ever
reaches `ContextDensityEngine` or `ContextCompilerV2`. A short, low-overlap
prompt like "Our decision is to use SQLite." does not share enough surface
vocabulary with the stored memory's phrasing to pass the filter, even
though it is the exact required answer.

## Why this is not the same bug as the one already fixed this session

Earlier this session, commit `d965015` fixed a **different** defect in the
same file: a broad "critical" need category was blanket-*bypassing* the
relevance filter, causing **over-inclusion** of irrelevant candidates. That
fix did not move the (separate) `phase15-corpus-v2` numbers noticeably.

This investigation's finding is the **opposite-direction twin**: on short,
low-overlap-but-correct real-shaped prompts, the same filter
**over-excludes** — it drops the genuinely correct candidate. Two defects
in the same component pulling in opposite directions (over-inclusion in
one case shape, over-exclusion in another) is a stronger signal than either
alone: it says the lexical/term-overlap relevance *scoring itself* — not
one specific threshold or category rule — is not a reliable filter for
short, real-shaped prompts.

## Classification

**Structural limitation of the current design, not a narrowly-fixable
defect**, per the contract's own allowed outcomes (§"Required evidence,"
item 3: "Either answer is a valid, complete result of this contract").

Reasoning for this classification rather than "genuine defect, propose a
fix":

1. The fix that worked last time (narrowing an over-broad bypass condition)
   does not transfer here — there is no analogous single condition to
   narrow. The filter's core scoring mechanism (lexical/term-overlap) is
   what fails, not a misconfigured guard around it.
2. Any fix aimed at *this* case (e.g., loosening the relevance threshold,
   or adding another bypass category for "explicit decision" phrasing)
   would be exactly the kind of case-specific patch the earlier
   over-inclusion bug came from — it would trade one direction of error for
   the other, not fix the underlying scoring approach. That is a redesign
   of `retrieval_decision_v2`'s relevance model, not a bounded diagnosis-
   contract patch, and is explicitly out of this contract's scope ("Widening
   into a general V2 refactor... stop and report that finding plainly
   instead of expanding scope").
3. Wiring the stage in matches production (`compile_task`) exactly, and
   still loses to the *unwired* eval-only shortcut on this corpus — meaning
   IG01-F's original finding ("V2 underperforms V1 and Recency") is not an
   artifact of the eval harness omitting a step; it holds (and is slightly
   worse) even when the eval harness is corrected to match production.

## What this settles and what it doesn't

- **Settles:** the `CompilerV2ContextProvider` missing-`selection=`
  discrepancy between eval code and production code is real (confirmed by
  direct comparison) but is **not** the cause of IG01-F's V2 regression —
  if anything, matching production makes the measured regression larger.
  `COMPILER_CAPABILITIES`'s `"task_aware_ranking": "supported"` claim in
  that eval provider remains inaccurate independent of this finding, but
  fixing that eval-only wiring gap is not a fix for the regression itself.
- **Settles:** V2's underperformance on `ig01f-recency-v1` is consistent
  with a structural weakness in `retrieval_decision_v2`'s lexical relevance
  filter, evidenced on two independent corpora in opposite failure
  directions, not corpus-specific noise.
- **Does not settle:** whether a redesigned relevance-scoring approach
  (e.g., semantic similarity instead of, or blended with, term overlap)
  would close the gap. That is a design question for a future, separately
  authorized package — not something this read-only contract can answer
  without prototyping changes to V2, which is out of scope here.
- **Does not authorize:** any V2 tuning, promotion, or Phase 20 change.
  Phase 20 remains FROZEN; V2 remains SHADOW.

## Evidence artifacts

- `evals/ig01f-investigation/compare_v2_probe.py` — the A/B probe
  (read-only; must be run from a checkout of `ig/ig01f-naive-baseline`,
  see its own docstring).
- `evals/ig01f-investigation/raw_comparison.json` — raw per-case metrics
  for both providers across all 114 DEV+VALIDATION cases (no HOLDOUT).

## Regression-test design (for a future fix package, not applied here)

Not proposing a fix in this contract (see Classification above), but for
whoever scopes the follow-up redesign: the reproducing case above
(`ig-eval-v2-explicit_decision-en-2`) is a ready-made regression case —
any redesigned relevance filter should be required to retrieve
`mem-ig01f-1228824e693370d3982a` for the prompt "Our decision is to use
SQLite." without regressing the over-inclusion case `d965015` already
fixed.
