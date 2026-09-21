# CANARY gate feasibility — proposal for independent review

**Status: PROPOSAL (sections 1–4), with the owner's decision recorded in section 5.** It is
not a contract and not completion evidence. The proposal itself changes no threshold, corpus,
code path or authority, and it does not reopen Phase 20 or promote V2. Classification in `DOCUMENTATION-AUTHORITY.md` is left to
the owner; until then it defaults to HISTORICAL by path rule 7.

**Özet (TR).** Canonical hafızaya yeni kayıt kabulü (`review accept`), CANARY moduna
bağlı; CANARY ise dondurulmuş holdout kalite kapısına bağlı; o kapı ise kullanıcıya
teslim edilmeyen bir V2 hattını ölçüyor. Kapının precision eşiği (≥0.70), public
suite'te ölçtüğüm dört sinyalle (mevcut kelime örtüşmesi, tüm-vault IDF, e5-base
embedding, IG-01d'deki üç model) ulaşılabilir görünmüyor. Bu belge, eşiği gevşetmeden,
hangi kararın kimin olduğunu ve seçenekleri ortaya koyar.

## 1. What is coupled to what

| Fact | Where (symbol, not line) |
|---|---|
| Entering CANARY runs the frozen holdout gate and refuses on anything but `PASS` | `RuntimeConfig.set_mode`, `brain_eleven/runtime/storage.py` |
| Accepting a review candidate into canonical memory requires CANARY or ACTIVE (rejecting does not) | `review_action`, `brain_eleven/runtime/service.py` |
| The gate measures `compile_task`, documented as the historical V2 compatibility API "for offline evaluation only"; native delivery never calls it | `compile_task`, `brain_eleven/runtime/context.py` |
| Model-facing providers are V1 and W06B_TASK_AWARE only; normal-turn context is withheld in SHADOW | `MODEL_FACING_V1_PROVIDERS`, `compile_context`, same file |
| The gate's seven checks (precision ≥ 0.70, required recall ≥ 0.80, three safety zeros, two non-regression vs V1) | `run`, `evals/runtime_eval.py` |

Consequence observed on 2026-09-20: mode `SHADOW`; canonical store last validated
2026-09-04; review queue 249 items, 248 `PENDING`, newest from that day. The capture
pipeline works; nothing can be accepted, so nothing reaches canonical memory, so new
sessions see only the 4 September snapshot. A fresh-session recall test scored 0/5
from memory (see `TEST-LOG.md`).

Current gate result (holdout, `canary-quality.json`): runtime precision 0.169, recall
0.676; V1 0.173 / 0.706. The three safety checks pass (no forbidden, project or
lifecycle leaks). Public suite: runtime 0.188 / 0.714, V1 0.180 / 0.747.

## 2. Evidence that the precision threshold is not reachable

All on the **public** suite (130 cases, 123 with a real-candidate choice), offline,
no production code changed. Method: replay the `compile_task` chain up to
`RetrievalDecisionEngine`; eligible = selected candidates plus those dropped only for
`INSUFFICIENT_TASK_RELEVANCE`; gold = `required ∪ useful`; noise ids start `noise_`.

| Signal | MRR of first gold among real candidates | Gold strictly above all noise |
|---|---|---|
| Term overlap (current, pool IDF) | 0.499 | 0.8 % |
| Term overlap, vault-wide IDF | 0.503 | 1.6 % |
| `intfloat/multilingual-e5-base` cosine (rev `d128750`) | 0.472 | 22.0 % |
| Random order (expected) | 0.487 | — |

- A selector with **perfect noise removal but no ability to choose among real
  memories** reaches precision **0.211** and required recall **0.779**. The gate asks
  for 0.70 and 0.80. No margin threshold on the embedding signal exceeded 0.211.
- The required memory never enters the candidate pool in **33 / 130** cases, so
  candidate generation (`context_router`, term/substring matching), not the decision
  stage, caps recall at 0.779.
- Prompts are templated ("...for eleven_capture relevance scenario 1.") and carry no
  information that separates the required record from the ~4.5 real candidates.

This matches `D0-RECHECK-FINDINGS.md` §1 (thresholds above the oracle ceiling on that
corpus) and IG-01d's three embedding models (roughly half of the ceiling, inconsistent
across models).

**Limits.** One embedding model; synthetic, templated corpus; the holdout ceiling was
**not** measured. Transparency: while diagnosing I inspected one holdout case in
detail (`p15_v2_authority_traps_041`) and read the gate's own per-case report. Later
work used the public suite only. A reviewer should weigh that.

## 3. Options (owner and reviewers choose; none is implemented)

**A. Status quo.** Keep the coupling. Review-accept stays locked, canonical memory
stays frozen at 2026-09-04, sessions keep receiving the old snapshot. Honest but it
means the system cannot learn from new sessions until the gate is reachable.

**B. Allow `accept` in SHADOW for human-reviewed candidates.** The quality gate keeps
governing CANARY (normal-turn delivery) and any V2 promotion. Rationale: `accept` is
already human-approved (`b1_human_approval`), and the delivered path is V1/W06B over
the same canonical store; SessionStart bootstrap already reads that store in SHADOW.
Risks: SHADOW stops meaning "no canonical writes"; capture precision is unmeasured
(one earlier 2.98 MiB real session produced 62 candidates, `SRT00-PLAN.md`), so
review is the only guard. No existing test asserts the SHADOW refusal (the message
occurs only in `service.py`; the accept tests run under CANARY), so the current
behavior is untested and a change would need new SHADOW tests. Secret/safety filters
stay in force. Needs its own contract, tests and independent review.

**C. Measure the delivered path with a feasible metric.** Replace the gate's target
with V1/W06B and normalise precision by the oracle ceiling (as `D0-RECHECK-FINDINGS.md`
proposes: precision@min(k, |relevant|)). Requires a new frozen threshold justified by a
ceiling analysis and a new holdout seal. This is an evaluation-contract change and
therefore heavier than B; it also touches the "no new eval set" boundary the owner set
for this sprint.

**D. Ceiling audit first.** Before choosing, have a reviewer with legitimate holdout
access measure the holdout's precision/recall ceiling using the method in section 2.
If the holdout ceiling is also below 0.70, the gate is infeasible by construction and
the choice is between B and C; if not, this proposal's premise is weaker than stated.

**Lean (opinion, not a recommendation to bypass anything).** D, then B: smallest change
that serves the stated goal (new sessions remembering) without touching a threshold,
the frozen corpus, or the gate's role for normal-turn delivery.

## 4. What this proposal does not do

No threshold lowered, no case skipped, no corpus or holdout label touched, no mode
changed (the repeated `set_mode('CANARY')` attempts were refused by the gate itself and
left `SHADOW` in place). An unrelated, tested fix to `retrieval_decision_v2/engine.py`
(a broad "critical" category no longer bypasses the relevance filter) was committed
separately; it did not move the gate numbers and is not part of this proposal.

## 5. Decision (owner, 2026-09-21)

The owner chose **option B**, as an explicit flag rather than a change of mode semantics.
`shadow_accept` (off by default; `python -m brain_eleven shadow-accept ON|OFF`) lets a person
accept a reviewed candidate while the runtime stays in SHADOW. What did **not** change: the
quality gate still governs CANARY and any V2 promotion, no threshold or corpus was touched,
the automatic worker path never uses the flag, and it never applies while the runtime is OFF.
The SHADOW refusal of accept, which had no test, now has one in each direction
(`tests/test_shadow_accept.py`). The flag has not been enabled by the assistant and the change
still needs an independent review before it counts as shipped. Option D (a holdout ceiling
audit by someone with holdout access) remains open and unaffected.
