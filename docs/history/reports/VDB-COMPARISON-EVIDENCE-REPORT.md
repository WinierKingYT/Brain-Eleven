# External comparison: Ahmet's "vdb" project vs. Brain-Eleven's IG01E retrieval

**Status:** COMPLETE, READ-ONLY EXTERNAL COMPARISON. No Brain-Eleven production
code changed. Does not authorize any integration, dependency addition, or
retrieval-architecture change — Phase 20 stays FROZEN, V2 stays SHADOW.
Written 2026-09-23.

## Why

Ahmet has two separate, mature personal projects unrelated to Brain-Eleven:
"PMIRI" (a local-first evidence/retrieval runtime) and a Qdrant-based
"Kişisel Vektörel Veritabanı" ("vdb"), reviewed together with Claude earlier
in this session. Ahmet asked whether integrating either with Brain-Eleven
would be worthwhile "maliyeti aşırıya kaçmadıkça önemli değil" (as long as
the cost isn't excessive, it's fine even for modest benefit). Claude's
assessment: PMIRI functionally overlaps with Brain-Eleven's own
authority/evidence layer (no clear benefit regardless of cost); vdb's
**abstention calibration** concept was interesting and directly relevant to
today's `WEAKNESS-IG01F-V2-REGRESSION-INVESTIGATION-EVIDENCE-REPORT.md`
finding that `retrieval_decision_v2`'s lexical relevance filter is
unreliable in both directions. Rather than guess whether vdb's retrieval is
actually better, this ran a bounded, reversible, read-only comparison: same
real content, same real queries, same scoring code as Brain-Eleven's own
`evals/ig01e_real` probe (IG01E Run 2, `precision_at_min5_relevant = 0.9167`).

## Method

1. `prepare_sources.py` wrote IG01E-real's 48 fixture memories
   (`evals/ig01e_real/fixtures/real-content-v1.json`, the same content used
   for Brain-Eleven's own 0.9167 result) as individual files.
2. Ingested into an **isolated** vdb collection
   (`VDB_COLLECTION_NAME=brain_eleven_ig01e_eval_v1`, a separate
   `VDB_DATA_DIR`/`VDB_QDRANT_URL`) — vdb's own production data/collection
   was never touched.
3. `run_search.py` ran all 21 IG01E-real task prompts
   (`evals/ig01e_real/tasks/real_*.json`) through `vdb search --limit 5`,
   once dense-only and once with `--rerank` (`VDB_RERANKER_MODE=lexical`).
   Result files are `results-dense.json` / `results-lexical-rerank.json` in
   this directory.
4. `score_results.py` scores both with Brain-Eleven's own, **unmodified**
   `evals.ig01d.d0_recheck._metric_row_recheck` — the exact function behind
   IG01E's own `precision_at_min5_relevant` number, so results are directly
   comparable, not just similarly-named.

Both projects use the same embedding model and revision
(`intfloat/multilingual-e5-base`, `d128750597153bb5987e10b1c3493a34e5a4502a`)
— confirmed by inspecting vdb's `.env.example` against
`docs/history/evidence/TEST-LOG.md`'s own recorded model/revision. This
means the comparison isolates architecture/calibration differences, not
embedding-model choice.

## Result

| Variant | `precision_at_min5_relevant` | forbidden leakage (21 cases) |
|---|---|---|
| **Brain-Eleven IG01E Run 2** (MPNet + neural cross-encoder rerank) | **0.9167** | 0 |
| vdb, dense only (e5-base, no rerank) | 0.8333 | 1 (`real-001`) |
| vdb, dense + lexical-overlap rerank | 0.7143 | 1 (`real-001`) |
| (reference) D0, old synthetic corpus, MPNet | 0.2597 | — |

Full aggregate metrics (`precision_at_5`, `recall_at_5`, `mrr`) are
reproducible from `score_results.py` against the committed result files.

## Findings

1. **No evidence justifies integrating vdb's retrieval into Brain-Eleven.**
   Neither vdb variant beats Brain-Eleven's own best measured result (0.9167)
   on the same content and queries. The dense-only variant (0.8333) is the
   closer of the two, but still lower, and with a leakage event Brain-Eleven's
   probe didn't have.
2. **Independent, second confirmation of today's IG01-F finding.** vdb's
   `--rerank` uses a `LexicalOverlapReranker` (token/Jaccard overlap, not a
   neural cross-encoder) — enabling it made the result *worse* (0.8333 →
   0.7143), the same direction as `retrieval_decision_v2/engine.py`'s
   lexical relevance filter being found unreliable today, but from a
   completely unrelated codebase and author. This strengthens, rather than
   merely repeats, the conclusion that lexical/term-overlap scoring is a
   structurally weak choice for this kind of relevance judgment, not a
   Brain-Eleven-specific implementation bug.
3. **Both vdb variants still strongly beat the old D0 synthetic-corpus
   number (0.2597).** Consistent with everything else found this session
   (IG01E Run 1/2/3, this comparison): retrieval over real content is not
   fundamentally broken by any measure tried so far; D0's low number was a
   property of that corpus/methodology, not of "retrieval on real content."
4. **The abstention-calibration *idea* remains untested here** — this
   comparison measured vdb's raw ranked output, not its calibrated
   abstention threshold (`vdb abstention-calibrate` needs a labeled
   validation split with negative/irrelevant examples, which IG01E-real's
   21-case fixture doesn't currently have in that shape). The concept is
   still worth keeping as a reference for `retrieval_decision_v2`'s eventual
   redesign; this comparison only tested vdb's ranking/reranking, not that
   specific mechanism.

## Conclusion

**PMIRI: not pursued** (functional overlap with Brain-Eleven's own
evidence/authority layer, no benefit case). **vdb: tested, not adopted** —
the bounded experiment Ahmet approved gave a real, negative answer rather
than a guess. No integration, no new dependency, no code change to Brain-
Eleven's retrieval. The one thing worth keeping from this is now written
into `🗂️ Proje Notları/Referans/vektörel-veritabanı - abstention
calibration.md` as a still-speculative, not-yet-tested-here idea for a
future `retrieval_decision_v2` redesign — separate from and not advanced by
this comparison.
