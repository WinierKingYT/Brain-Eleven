# IG01E-real — two runs, and the honest remaining confound

**Status:** GENERATED EVIDENCE — a first-pass proof-of-concept, now with a
scale-up control. Does not reopen or settle the D0/D1 retrieval-quality
question by itself. Written 2026-09-12.

## What was built

`evals/ig01e_real/` is a new, separate evaluation package (does not touch
the frozen `evals/ig01d/` contract). It contains:

- `fixtures/real-content-v1.json` — **48** candidate "memory" records drawn
  from actual vault content: all 15 real `minecraft_mcp` ADRs, all 5 real
  `pet_sistemi` ADRs, `promackro`'s and `promtgen`'s real decisions (1 and 2
  respectively — those projects genuinely have few recorded decisions, which
  is itself an honest fact, not a corpus gap), and 24 global items (17
  `Referans/` pattern notes, 2 `Dersler/` lessons, 5 root IG-program
  decisions) — replacing the old fixture's 38 hand-written, English-only,
  fictional-project one-liners (`evals/fixtures/phase15-contract.json`).
- `tasks/real_001.json` … `real_018.json` — 18 natural-language prompts
  (genuine Turkish/English mix), hand-labeled `required`/`useful`/`forbidden`.
- `run_real_probe.py` — reuses `evals.schema`, `evals.fixture_generator`,
  and `evals.ig01d.spike`/`d0_recheck`'s exact ranking and metric code
  (`precision@min(5,|relevant|)`) without modifying either file.

## Two runs: the scale-up control

**Run 1** (14 tasks, 25 memories, ~13-19 candidates per task):
`precision@min(5,|relevant|)` = **0.9286**.

That number was flagged as not yet trustworthy — it could have been an
artifact of a too-small, too-easy candidate pool (the old D0 corpus forced
`noise_count=24` synthetic distractors into every case; this corpus started
with `noise_count=0` and few candidates per project).

**Run 2** (18 tasks, 48 memories — nearly 3x the candidates for
`minecraft_mcp`, 2x for `pet_sistemi` and the global scope, still
`noise_count=0`): `precision@min(5,|relevant|)` = **0.9167**. Barely moved.

| Metric | Run 1 (25 mem) | Run 2 (48 mem) | Old corpus (ig01d, D0 recheck) |
|---|---|---|---|
| `precision@min(5,\|relevant\|)` | 0.9286 | 0.9167 | 0.2597 |
| `recall@5` | 1.0 | 1.0 | — |
| `mrr` | 0.9643 | 0.9722 | — |
| Safety leakage (all 4 categories) | 0 | 0 | 0 (comparable) |

Per-case (Run 2): 16 of 18 perfect, 2 partial misses (`real-003`,
`real-006`) — both near-misses (correct item found at rank 2, not a
complete failure), not systematic breakdown.

**Conclusion of the scale-up control: candidate-pool size was not the
main driver.** Nearly tripling the hardest project's candidate count changed
the result by 0.012, not by the kind of swing you'd expect if the earlier
0.9286 were mostly a "too few options to get wrong" artifact.

## The confound that's actually left, and it's a different one

Ruling out pool size points at a more mundane and more important
limitation: **these 18 queries were authored by the same process, in the
same pass, with full knowledge of the fixture content and the gold labels**
— unlike D0's corpus, which was built from a separately-authored template
generator with no human hand-picking phrasing per case. Writing a query
right after reading the memory it targets naturally produces vocabulary
overlap with that memory's content (e.g. "neden WAL modlu SQLite seçildi"
echoes the ADR's own wording almost directly). This is a real, well-known
eval-design bias — it is not the same failure mode D0 had (a corpus-wide
metric/ceiling design flaw), but it means **this specific 0.92 is
optimistic about how vault content will paraphrase-match a user's actual,
independently-phrased question**, which is the harder case production
retrieval actually needs to handle.

## What both runs do support

- The harness works end-to-end at production-realistic candidate density
  (48 real memories, up to ~38 candidates for a single scoped query) with
  zero code changes to `evals.schema`/`evals.fixture_generator` and zero
  new metric logic.
- Zero safety leakage across both runs.
- MPNet is not fundamentally broken at finding a real, correctly-worded
  decision among dozens of real, topically-clustered real distractors
  (e.g. `real-015` correctly separated ADR-0013 from four other real
  Maven/wrapper-themed ADRs in the same project).

## Recommended next step (done, partially — see Run 3)

The pool-size lever is now spent — scaling further without addressing
authorship bias will not change the diagnosis. The next experiment that
would actually move this forward: have someone who did **not** write the
fixture (or a separate subagent working only from a content summary, blind
to the exact memory wording) author the query set, so phrasing cannot
leak from label-writing into query-writing. Only that removes the
remaining confound and produces a number worth citing next to D0's 0.2597.

## Run 3 (2026-09-23) — independently-authored queries, the confound actually removed

Ahmet (the vault's owner, who did not write `real-content-v1.json` or its
labels) wrote 3 natural-language questions from memory, prompted only with
bare topic labels per project (not the recorded content, not the exact
wording) — the exact design this document called for above. Added as
`tasks/real_019.json`–`real_021.json`, all `minecraft_mcp`; labeled by this
session against the existing real fixture content, not by Ahmet. Measured
with `run_real_probe.py`, same models (MPNet embedding, mMiniLMv2
cross-encoder), same metric, no changes to the harness.

| Task | Prompt (as written, minor spelling kept) | Rank of the correct memory | recall@5 |
|---|---|---|---|
| `real-019` | "Protokol neden durumsuz?" | **1** (MRR 1.0) | yes |
| `real-020` | "Neden wrapper guven modelini sectik?" | **1** (MRR 1.0) | yes |
| `real-021` | "Supervisor mekanizmasi neden boyle?" | 2 (MRR 0.5) | yes |

2 of 3 exact top-1 hits, 1 of 3 a near-miss (found at rank 2, not missed
outright), 3 of 3 recall@5, 0 leakage of any kind across the full 21-case
run this batch was part of.

**This is a small sample (n=3) — not a number to cite as a program-wide
metric, and it does not reopen or settle D0/D1.** What it does show,
honestly: with the authorship-bias confound actually removed, the real
result is still strong, not close to D0's 0.26. The retrieval mechanism
itself (semantic search over real vault content) is not the thing standing
between this project and a working recall test — what's standing between
them is that no production delivery path runs a query like this at all
today (`SessionStart` serves a frozen 2026-09-04 snapshot; see
`TEST-LOG.md`). More independently-authored questions, across more
projects, would firm this number up further; it is not currently
blocking anything.
