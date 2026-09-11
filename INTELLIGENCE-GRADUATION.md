# Intelligence Graduation (IG)

Authority: **CONTRACT**. Program decision: 2026-09-07. Execution status belongs
to [PROJECT-STATUS.md](PROJECT-STATUS.md); evidence belongs to each package.

## Purpose and invariants

Phase 20 / Knowledge Engine is **FROZEN**: a feature freeze, not a completed
intelligence milestone. Preserve its future designs. Make the existing memory
system reliably capture, retain, correct and retrieve the right information in
daily work before unlocking it. Infrastructure, test counts and green CI do not
prove intelligence quality.

- **IG-INV-01:** No Knowledge Engine, Autonomous Planner, Cognitive Controller,
  Outcome Learning, new graph reasoner, product agent framework or persistence
  authority. Bounded bug fixes, reliability, evaluation, migration and intelligence
  work are allowed. Engineering review agents are not a product feature.
- **IG-INV-02:** MemoryStore, StateStore and ProjectRegistry remain canonical
  authorities. Derived graphs, telemetry and models cannot replace them.
- **IG-INV-03:** Evidence → structured model proposal → deterministic validation
  → truth/lifecycle resolution → canonical commit. Never direct model writes.
- **IG-INV-04:** Safety and intelligence are measured separately. Locking, CAS,
  schema, isolation, secrets and backup correctness cannot substitute for quality.
- **IG-INV-05:** Shadow is temporary. Graduation requires V2 production and V1
  retirement, or an explicit failed-V2 architectural reassessment. No perpetual
  V1-active/V2-shadow program alongside later phases.

## Sequential execution and ownership

Every package follows read-only audit → bounded contract → implementation →
focused tests → full regression → independent read-only review → SHIP / FIX-FIRST /
RETHINK. Only accepted package closure permits the next package. No mega rewrite,
unrelated cleanup, model-first replacement or test-count optimization.

The engineering orchestrator coordinates read-only and does not write production
code. Repository research is targeted to the package, not repeated whole-repo
audits. The implementation agent owns only its bounded contract. Evaluation work
must measure production behavior. Independent reviewers examine contract, diff,
tests, failures and evidence, preferably without inheriting implementation reasoning.

Use small commits for contract, implementation, evaluation, integration and fixes;
never one program-sized commit. Each implementation reports changed files, why,
added/executed tests, results and limitations. Each review reports compliance,
regressions, authority violations, missing tests and failure modes.

## Packages and exit gates

| Package | Bounded work and required exit evidence |
|---|---|
| **IG-00 Freeze & Baseline** | Freeze Phase 20; bind an exact known-green baseline to matching CI before creating `intelligence-graduation-baseline`; map actual runtime, installed versus repository paths, V1/V2 ownership and documentation authority. No closure without these facts and review. |
| **IG-01 Product Evaluation Foundation** | Deterministic retrieval, extraction and correction corpora; public synthetic, private realistic and growing sanitized real-failure sets; realistic distractors; separately measured V1/V2 baselines; evaluation that penalizes selecting everything. Establish answerable labels and version/split provenance before tuning. |
| **IG-03 Semantic Extraction** | Deterministic prefilter → semantic structured propositions → deterministic validation. Preserve candidate/project/evidence identity, kind/claim key, subject/predicate/value, commitment/time, confidence components, target/reason and source role as applicable. Model proposes only. Beat regex baseline; distinguish questions, hypothetical/quoted text and assistant proposals from explicit user decisions, preferences, lessons and typed state. Contract acceptable false commitment rates before evaluation. |
| **IG-02 Autonomous Capture Closure** | Real hook → durable queue → worker → evidence → extraction → truth/state → canonical effect → terminal queue outcome. Verify automatic draining, at-least-once/idempotent delivery, bounded retry, dead-letter visibility, leases, crash recovery, retention, error codes and observability. Golden E2E starts with “PromtGen authentication için session cookie kullanacağız.” and observes canonical memory. A COMPLETED job is not itself proof of a canonical effect. |
| **IG-04 Reference, Correction & Lifecycle** *(superseded scope — see note below)* | Resolve within project using conversation lineage, claim, similarity, time and lifecycle. Outcomes RESOLVED_TARGET / AMBIGUOUS / NO_TARGET / REVIEW_REQUIRED; ambiguity never guesses. Distinguish CONFIRM, SUPERSEDE, RESOLVE, CORRECT and REOPEN. Direct, conversational and claim targets tested; inactive/cross-project targets and cycles protected; false supersession is a hard gate. |
| **IG-05 Task-Aware Retrieval Quality** | Task → needs → candidates → scope → authority/lifecycle → relevance/diversity → minimum sufficient context → compiler. Explain task/claim/project relevance, criticality, authority, freshness, dependencies, historical importance and redundancy. Old critical decisions beat fresh irrelevant facts. Meet precision and mandatory recall gates, beat V1, reduce noise and preserve zero forbidden/project/superseded/resolved leakage. |
| **IG-06 V2 Runtime Integration** | Only after IG-05: SHADOW → MIRROR → CANARY → DEFAULT → V1 FALLBACK → RETIREMENT CANDIDATE. Shadow sends V1 only and measures V2 content-free. Canary is Brain-Eleven only. Verify single-gate V2→V1 rollback, authority/isolation, budget and startup degradation before default V2 delivery, including SessionStart. |
| **IG-07 Architecture Consolidation** | Move implementation authority into logical `brain_eleven` capture/evidence/extraction/memory/state/retrieval/authority/compiler/lifecycle/projects boundaries. Scripts become adapters/operations/migrations. No copied competing implementations; minimize legacy loaders and hyphenated implementation authority. Clean imports and full regression required. |
| **IG-08 Real-Use Dogfood & Failure Mining** | Repeated real workloads, project switches, corrections and long sessions; sanitized failure corpus; close P0/P1 intelligence bugs and unexplained persistent retrieval regressions. No invented usage and no replacement of behavior evidence by elapsed days. |
| **IG-09 Graduation Audit** | Read-only independent audit of capture/crash/replay, semantic extraction/uncertainty, correction/ambiguity, retrieval/noise, safety, single package authority, rollback, backup and observability. Independent SHIP required. |

IG-00 through IG-06 are P0 Phase 20 blockers. IG-07/08 are P1 graduation
blockers. Cosmetic documentation, developer UX, noncritical performance and API
expansion can wait. IG-09 cannot implement its own fixes; findings return to
bounded corrective work and a fresh review.

## IG-04 pivot: Branch B (2026-09-10)

`CODEX-RESULTS-D0.md` measured the embedding-similarity retrieval approach
this program originally planned to build IG-04 through IG-09 on top of, and
found it does not graduate (empirical ceiling below 0.45). Its D1 decision:
**Branch B** — automatic capture stays, but retrieval eligibility is gated on
an explicit human approval step, not on retrieval-quality tuning. **IG-04's
slot is now the Branch B track**, not the reference/correction/lifecycle work
described in its original row above. That original scope is not deleted —
it's deferred; a real reference/correction problem still exists and may
reopen as a later package once Branch B's daily-use quality is established.

Branch B is delivered as lettered sub-packages under IG-04:

| Sub-package | Scope | Status |
|---|---|---|
| **B1 — Human-approved retrieval boundary** | A captured candidate cannot affect retrieval until an explicit accept action. See `IG04-B1-CONTRACT.md`. | CLOSED / SHIPPED — independent review `SHIP`, see `IG04-B1-INDEPENDENT-REVIEW.md`. |
| **B2 — Review queue usability** | Makes B1's review queue actually usable day to day: dedup near-duplicate pending candidates, order the queue so the most decision-worthy items surface first. See `IG04-B2-CONTRACT.md`. | CLOSED / SHIPPED — independent review `SHIP`, see `IG04-B2-INDEPENDENT-REVIEW.md`. |

IG-05 through IG-09 remain closed until Branch B's daily-use quality is
established (per D1) — not merely until B1 or B2 ship. That determination is
a later, explicit call, not automatic on B2's closure.

### D0 recheck (2026-09-12) — the evidence behind D1 needs a second look

`D0-RECHECK-FINDINGS.md` independently re-derives D0's own numbers and finds
two problems with the evidence D1 was based on, both verified directly
against the code by this session (not taken on a subagent's word): the
0.45/0.60 thresholds are below/at the mathematical ceiling of D0's own
scoring metric on its own corpus (an oracle retriever scores 0.425 mean, not
1.0), and the "hybrid doesn't help" finding fused real semantic search with
a control arm (`BaselineContextProvider`) that is documented to never see
the query at all. Separately, the production V1 path that actually runs
today never used embedding retrieval in the first place, so D1's pivot away
from it changed nothing about current user-facing quality either way. This
does **not** reopen D1 by itself — Branch B (human-approved retrieval)
remains closed, accepted, and valuable regardless — but it means the
"embedding retrieval caps at 0.20 against a 0.60 floor, abandon it" framing
overstates the case. Two cheap, infrastructure-free recheck experiments are
proposed in that document; their results are the next real input to whether
D1 should be revisited.

## Evaluation contract to establish in IG-01

Retrieval covers exact/related relevance, recent distractors, old critical
decisions, foreign projects, superseded/resolved records, preferences, lessons,
current state and history. Extraction covers decision, suggestion, hypothetical,
question, correction, negation, preference, lesson, requirement, blocker/resolution,
assistant proposal and quotation. References include “önceki karar”, “onu iptal
et”, “bunu kullanalım”, named JWT corrections and prior-design references.

Report precision, recall, F1, MRR/rank quality, noise and mandatory recall;
decision precision/recall, false commitments, assistant-as-user errors, correction
detection and state/memory routing; correct targets, ambiguity abstention and
false supersession. All four safety leakage classes remain zero.

Program production targets are context precision **≥ 0.60**, mandatory recall
**≥ 0.80**, V2 precision **strictly above V1**, and V2 recall at an explicitly
accepted V1-equivalent threshold. IG-01 must bind that remaining threshold,
denominators, corpus versions and split policy before intelligence tuning.
These are program targets, **not a claim that the existing PRE-13 ≥ 0.70 runtime
promotion gate has changed**. Recalibration requires an explicit versioned
contract and preserved prior results; never relabel or use holdout answers to
make a failing implementation pass.

Required capture faults include crashes after evidence read, before and after
canonical write, lock timeout, corrupt/deleted transcript, invalid project,
duplicate/replayed events, corrupt queue and StateStore conflict.

Dogfood failures use CAPTURE_MISS, FALSE_CAPTURE, WRONG_TYPE, WRONG_SCOPE,
WRONG_TARGET, FALSE_SUPERSESSION, RETRIEVAL_MISS, RETRIEVAL_NOISE,
AUTHORITY_ERROR, STALE_CONTEXT and TOKEN_WASTE. Retain only privacy-safe usage
metadata (counts, selected IDs/hashes, ranking signals, size, abstention,
fallback and latency); raw prompts/memories are not long-term telemetry.

## Phase 20 unlock

All capture, semantic extraction, calibrated uncertainty, safe correction,
task-aware retrieval, minimum-context superiority, V2 production/rollback,
bounded architecture debt, real failure closure and independent SHIP gates
must pass. Any open P0 keeps Phase 20 **LOCKED**. P1 graduation blockers must
also close. Preserve Phase 20 designs until this decision; do not start them
as groundwork during IG.
