# IG01-F V2 Regression Investigation Contract

**Status:** APPROVED CONTRACT — owner-authorized 2026-09-23 in response to
`IG01-F` issue [#2](https://github.com/WinierKingYT/Brain-Eleven/issues/2)
("F3: triage V2 regression versus recency-favorable baseline")
**Package:** read-only diagnosis, no tuning
**Priority:** P1 — informs whether V2 is worth continuing to invest in at all
**Phase 20:** FROZEN / LOCKED — **V2:** SHADOW (unchanged by this contract)

This is the separately scoped investigation package `IG01-F-PACKAGE-REPORT.md`
and issue #2 both say must exist before any V2 remediation. It does not
reopen or modify `IG01-F`'s frozen pre-registration, corpus, evidence, or
verdict, and it does not by itself authorize any change to V2.

## What triggered this

`IG01-F`'s frozen, pre-registered comparison (branch
`ig/ig01f-naive-baseline`, independently reviewed `SHIP` at `498e009`) found,
on its own `ig01f-recency-v1` DEV+VALIDATION corpus (no HOLDOUT read):

- **F1**: aggregate — Recency (a query-blind, "return the most recently
  updated scope-safe items" baseline) exceeds V2 on precision and recall.
- **F3**: on the four phenomena pre-classified as recency-favorable, Recency
  macro F1 is `0.333333` vs V2's `0.128205`; paired per-case F1 is **37
  Recency wins / 77 ties / 0 Recency losses** against V2.
- Reading the full per-phenomenon table (not just the four F3 phenomena):
  V2 is at or below V1 (the existing legacy compiler) on nearly every one of
  the 17 measured phenomena, often by a wide margin (e.g. `correction` F1:
  V1 `0.333`, V2 `0.056`; `lesson` F1: V1 `0.333`, V2 `0.048`). V2 also
  emitted an empty selection in all 6 abstention-set cases, where V1 and
  Recency emitted none.
- The `recency_continuity` provider's own capability declaration says
  `task_aware_ranking: unsupported` — it never reads the query. A
  query-blind heuristic beating a query-aware pipeline this broadly on a
  frozen, pre-registered, non-adversarial-to-V2 corpus is a strong signal
  that V2's selection stage, not the corpus, is where the loss is coming
  from — consistent with a real defect, not measurement noise.

This session already found and fixed one real, narrow defect in
`retrieval_decision_v2/engine.py` (a broad "critical" need category
blanket-bypassing the relevance filter — see
`docs/history/weakness/` W-07B commits and `TEST-LOG.md`'s retrieval
sections); that fix did not move the earlier `phase15-corpus-v2` numbers
noticeably, so if there is more here, it is probably a *different* defect,
not the same one measured again on a new corpus.

## Bounded objective

Find the actual, evidence-backed reason(s) V2 underperforms both V1 and the
query-blind recency baseline this broadly on `ig01f-recency-v1`'s DEV and
VALIDATION splits. Trace the real pipeline
(`context_router` → `authority` → `retrieval_decision_v2` →
`context_density_v2` → `context_compiler_v2`, as `compile_task` in
`brain_eleven/runtime/context.py` wires them) against specific losing cases,
not just the aggregate numbers. For each distinct root cause found:

1. State it precisely, with a specific reproducing case (phenomenon +
   case id) and the exact code location.
2. Classify it: a genuine defect (wrong behavior a fix could address without
   widening scope), or an inherent trade-off/limitation of the current
   design (would need a larger redesign, out of this contract's scope).
3. For a genuine, narrowly-fixable defect: propose the fix. Do **not** apply
   it without a separate go-ahead — this contract is diagnosis, matching
   issue #2's own "does not authorize tuning." If the fix is as narrow and
   clear as the earlier `retrieval_decision_v2/engine.py` finding, note that
   explicitly and ask whether to proceed as a follow-up, exactly like the
   capture-silent-gap handoff did.

## Scope

Allowed:

- Read `evals/ig01f/*` on `ig/ig01f-naive-baseline` (provider, corpus,
  measure, frozen evidence) to understand exactly what was measured — do not
  modify anything on that branch.
- Re-run the *existing* frozen IG01-F measurement locally, read-only, against
  DEV+VALIDATION only, to reproduce specific losing cases with full
  candidate-level detail (which candidates V2 saw, which it selected, why).
  Never open, read, or score anything under a `holdout` path.
- Read/trace `context_router/`, `authority/`, `retrieval_decision_v2/`,
  `context_density_v2/`, `context_compiler_v2/`, and
  `brain_eleven/runtime/context.py`'s `compile_task` wiring.
- Propose (not apply) a narrowly-scoped production fix if a genuine defect
  is found, with a regression test design.

Not allowed:

- Any change to `IG01-F`'s frozen pre-registration, corpus, evidence,
  provider code, or verdict on `ig/ig01f-naive-baseline`.
- Any threshold, evaluator, or budget change.
- Reading or scoring HOLDOUT, on this corpus or any other.
- Tuning, patching, or otherwise changing V2 production code as part of
  *this* contract — diagnosis and a proposed fix only; applying a fix is a
  separate, explicit follow-up decision.
- Promoting V2 from SHADOW, or touching Phase 20.
- Widening into a general V2 refactor. If the investigation implicates
  something bigger than a narrow, locatable defect, stop and report that
  finding plainly instead of expanding scope.

## Required evidence

1. Per finding: exact reproducing case(s), exact code location, and why the
   current behavior produces the measured loss — not a plausible guess.
2. If a fix is proposed: its exact diff (as a proposal, unapplied) and what
   regression test would prove it, matching this project's TDD convention.
3. A short report (this can be a comment on issue #2, or a new file under
   `docs/history/weakness/` if substantial) stating plainly: is V2's
   underperformance here explained by locatable, fixable defects, or does it
   reflect something more structural about the current V2 design? Either
   answer is a valid, complete result of this contract.

## Exit gate

This contract closes when the question above has an evidence-backed answer,
whether or not a fix is applied. It does not by itself authorize any V2
change, promotion, or new package — any follow-up (applying a proposed fix,
or a larger redesign) is a separate, explicitly authorized package, per
issue #2 and `docs/programs/WORK-INTAKE-RULE.md`.

**Status: APPROVED — investigation may proceed. Posted to issue #2 for
visibility per `CONTRIBUTING.md`'s GitHub-visibility practice.**
