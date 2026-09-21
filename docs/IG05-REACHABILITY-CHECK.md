# IG-05 reachability check — can the floors be met on `phase15-corpus-v2`?

**Status: GENERATED EVIDENCE / FINDINGS (2026-09-21).** Sections 1–5 are read-only analysis:
they change no floor, target, corpus or threshold, and they do not open or close IG-05.
Section 6 records the one code change the owner approved from that analysis (an opt-in,
default-off router tier); section 7 records the owner's decisions of 2026-09-21. The program floors are immutable (`IG01-A-EVALUATION-CONTRACT.md`,
"Verdict rule"); any change to them is a human checkpoint, not something this document
decides. Until classified in `DOCUMENTATION-AUTHORITY.md` it defaults to HISTORICAL by path rule 7.

**Özet (TR).** IG-05'in zemin eşikleri (macro precision ≥ 0.60 **ve** mandatory recall ≥ 0.80)
bu korpusta birlikte ulaşılamıyor: etiketleri ezbere bilen, sızıntılı bir üst sınır bile
0.565 precision'da 0.812 recall veriyor. Sebep bir seçici zayıflığı değil, korpusun yapısı:
aynı istem şablonunda yalnızca "scenario N" sayısı değişiyor ve gerekli kayıt N ile dönüyor;
sayı hiçbir kayıt içeriğiyle ilişkili değil. Tek meşru kaldıraç recall: kapsam-tabanlı aday
kümesi gerekli kaydı 130/130 vakada içeriyor (kelime tabanlı router: 97/130).

## 1. What was measured, and against what

| Item | Value |
|---|---|
| Corpus / fixture | `phase15-corpus-v2` (`evals/corpus-v2`), `phase15-contract.json`; **public suite, 130 cases**. Holdout not read. |
| Metric (contract) | context precision = `count(selected in required ∪ useful, not forbidden) / count(selected)`, **macro** mean over answerable cases, empty selection = 0 |
| Recall | mandatory recall = `required selected / required`, micro (as recorded by IG-01-D) |
| Program floors | precision ≥ 0.60, mandatory recall ≥ 0.80 (immutable) |
| IG-01-D provisional targets | 0.65 / 0.85, from the formula `max(floor + 0.05, baseline + 0.10)`; the report states **"no empirical ceiling is claimed"** (`SEMANTIC_UNAVAILABLE`) |
| Promotion gate | `V2_precision > V1_precision` and `V2_mandatory_recall ≥ max(accepted V1-equivalent, 0.80)` |

So the targets were derived by formula and never checked for reachability. This is that check.

**Harness fidelity.** The script reproduces the IG-01-D V1 baseline exactly (seed 17, noise 24):
macro precision **0.172308**, mandatory recall **0.714286**, both digit for digit.

## 2. Findings

**F1 — Recall is not information-limited.** A scope-complete candidate set (active memories of
the task's project plus global) contains every required memory in **130 / 130** cases. The
lexical router used by the V2 evaluation chain misses the required memory in 33 of 130
(earlier count, same suite). Candidate generation by scope, as the IG-05 chain already
describes ("task → needs → candidates → scope → authority/lifecycle"), is a legitimate lever.

**F2 — Precision is information-limited.** That candidate set averages 30.3 memories.

| Selector (label-free) | macro precision | mandatory recall |
|---|---|---|
| select all in scope (control) | 0.069 | 1.000 |
| perfect noise filter, all real memories | 0.113 | 1.000 |
| V1 (recorded, reproduced) | 0.172 | 0.714 |
| top-1 … top-4 by memory `confidence` | 0.050–0.062 | 0.03–0.11 |

`confidence` does not discriminate: the required memory is the top-confidence candidate in
**4 / 130** cases (median margin −0.159). Earlier measurements on the routed candidates add
that term overlap (0.499 / 0.503 MRR) and the `multilingual-e5-base` embedding (0.472) are at
chance (0.487) among real candidates (`docs/CANARY-GATE-FEASIBILITY-PROPOSAL.md`).

**F3 — The label is not a function of the prompt.** Same template, different required memory
(project `eleven_capture`, category `p15_relevance`):

| Prompt ends with | Required memory |
|---|---|
| … relevance scenario 1 | `mem_markdown_before_sqlite` |
| … scenario 4 | `mem_ec_local_cache` |
| … scenario 7 | `mem_ec_sqlite_index` |
| … scenario 10 | `mem_ec_atomic_rename` |
| … scenario 13 | `mem_ec_vault_manifest` |
| … scenario 16 | `mem_markdown_before_sqlite` (cycle repeats) |

The wording ("reliable persistence rule") is identical; only the counter changes, and the
required memory cycles through the project's memories. In 22 of 54 digit-stripped prompt
templates the cases disagree on the relevant set. No selector can know which memory is
required from the request text; it can only cover the candidates (recall) at the price of
precision, or memorise the counter-to-memory table.

**F4 — Frontier.** Best case for any selector that does not use the counter: a *leaky*,
in-sample lookup that already knows, per prompt template, which memories are most often
relevant (it uses the labels, so it is an upper bound, not a selector):

| Memories kept per template | macro precision | mandatory recall |
|---|---|---|
| 2 | 0.650 | 0.513 |
| 3 | 0.597 | 0.714 |
| **4** | **0.565** | **0.812** |
| 5 | 0.545 | 0.883 |

At recall ≥ 0.80 the bound is 0.565 < 0.60; at precision ≈ 0.60 recall is ≈ 0.71. **The floor
pair (0.60, 0.80) is outside the frontier and the provisional pair (0.65, 0.85) is further out.**
A selector that reads the scenario number could exceed this only by memorising the label
table, which is overfitting to the corpus and says nothing about retrieval.

## 3. What this does and does not show

- It shows the floors are not jointly reachable on this corpus by any selector that treats the
  scenario counter as arbitrary, and that no label-free signal tried separates the required
  memory from its siblings.
- It does **not** show IG-05 is impossible in general. The corpus is synthetic and templated;
  identifiability may exist on real data (`evals/ig01e_real`), which this check did not use.
- The relative gate (`V2_precision > V1_precision` at recall ≥ 0.80) is **not demonstrated** by
  any label-free signal. Recall ≥ 0.80 is reachable through scope-complete candidates, but then
  precision is 0.11 or lower, below V1's 0.172; only leaky selectors exceed it.
- Limits: public suite only (holdout ceiling unmeasured); all frontier numbers are in-sample
  upper bounds; one embedding model; one corpus.

## 4. Decision the owner needs to make (none is taken here)

`INTELLIGENCE-GRADUATION.md` states that IG-05 through IG-09 "remain closed until Branch B's
daily-use quality is established (per D1)" and that this is "a later, explicit call". The
2026-09-21 work order proceeds to IG-05 without recording that call.

Options, all outside this document's authority:

1. **Record the D1 call explicitly** and, if IG-05 opens, revise the target in the contract
   rather than in code: keep the relative gate (beat V1 precision at recall ≥ 0.80), and
   replace the absolute floors with a ceiling-normalised metric on a corpus where a ceiling
   exists (the direction of `D0-RECHECK-FINDINGS.md` §1).
2. **New corpus version** whose prompts determine the labels. Needs a contract, a corpus
   version bump, and a fresh holdout seal; it sits against the "no new eval set" boundary.
3. **Measure on real data first** (`evals/ig01e_real`), where identifiability can exist.
4. **Leave IG-05 closed** and continue with the recall test only.

Independent of the choice: scope-based candidate generation (F1) is a sound, low-risk
improvement to V2 recall, and it should not be tuned against the 0.60 floor.

## 5. Reproduction and transparency

```bash
python docs/evidence/ig05_feasibility.py   # about a minute, public suite, read-only
```

The script prints every number above. It hard-codes the public suite; a reviewer with holdout
access would change that deliberately to measure the holdout ceiling.

Transparency: earlier in this work one holdout case was inspected in detail
(`p15_v2_authority_traps_041`); this check used the public suite only. Two of my own
hypotheses were tested and refuted during the check (that `confidence` is the discriminating
signal; that the label depends on the project alone) and are reported as such.

## 6. Scope sweep: result (owner-approved 2026-09-21)

The one option chosen from section 4 was the candidate-generation lever from F1. It is an
**opt-in** tier in `context_router`: with `"routing": {"scope_sweep": true}` in
`.claude/context-router.json`, the router adds every active memory that is in scope (current
project plus global, lifecycle and profile memory types enforced by the existing `allowed()` /
`retrieve()` path) as a weak candidate after the lexical passes, with a score (0.10) below every
lexical score. It is **off by default**: candidate sets, plan fingerprints and cache keys of the
default configuration are unchanged (the flag enters the fingerprint only when enabled).

Public suite, same harness as above, flag off → on:

| | off | on |
|---|---|---|
| Router: all required memories among candidates | 97 / 130 | **129 / 130** |
| Average candidates per case | 4.8 | 20.0 |
| End-to-end V2 mandatory recall | 0.714 | **0.760** (V1 0.747) |
| End-to-end V2 precision (micro) | 0.189 | **0.159** (V1 0.180) |
| Forbidden / wrong-project / lifecycle leaks | 0 / 0 / 0 | 0 / 0 / 0 |
| Context p95 | 48 ms | 80 ms |

Reading it honestly: the lever does what F1 predicted for **coverage**, and end-to-end recall
rises above V1. It is not a free gain: precision falls below V1 by the same amount that F4's
frontier says it must. This is the recall/precision trade, not evidence of better selection.

- The one remaining miss (`p15_v2_cross_phase_traps_014`, a global lesson) is cut by the
  router's 20-slot memory budget: sweep-only candidates tie on score and the tie-break is the
  memory id. A prior for that tie-break was not added; `confidence` does not discriminate (F2).
- The decision stage still filters by lexical relevance, so most swept candidates never reach
  the final selection. A selection-stage policy that keeps more of them would move recall and
  precision along the frontier in F4; that is a separate choice and was not made here.
- Tests: 7 new router tests (default off, in-scope sweep, project isolation, lifecycle and
  profile types, candidate budget, boolean validation, plan/cache identity); router suite
  32 / 32; full unit suite 1451 passed, with only the known dirty-tree scope lock (five
  W-06C0R1 tests, which pass on a clean tree) and the timing-sensitive cold-start test failing.
- Measured on the public suite only. The holdout and Phase 17 router evidence were not used to
  tune anything.

## 7. Decisions taken (owner, 2026-09-21)

- **IG-05 is closed as unreachable on this corpus** (section 4, option 4 in spirit): V2
  stays SHADOW and is not promoted, IG-06 and IG-07 are not opened, Phase 20 stays LOCKED.
  No floor changed and nothing was tuned. Recorded in `INTELLIGENCE-GRADUATION.md` and
  `PROJECT-STATUS.md`.
- **Scope sweep stays off** (section 6).
- **Human-approved accept in SHADOW** was adopted behind a default-off flag; see
  `docs/CANARY-GATE-FEASIBILITY-PROPOSAL.md`, section 5.
- Still open, and not decided here: real-data measurement (`evals/ig01e_real`), a corpus
  version whose prompts determine its labels, and a holdout ceiling audit.
