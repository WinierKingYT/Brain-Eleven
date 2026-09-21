# W-06A Package Report — V1 SessionStart Bootstrap Ranking

**PACKAGE:** W-06A
**REVISION:** `8270fef`
**OBJECTIVE:** Make the active V1 SessionStart bootstrap ranking use bounded
current-project state relevance and deterministic tie-breaking without changing
V2, canonical authorities or Phase 20 state.

## FILES CHANGED

- `scripts/context-compiler.py`
- `tests/test_context_compiler.py`
- `evals/reports/baseline-v3.json` (deterministic source fingerprint refresh;
  metrics unchanged)
- `WEAKNESS-W06A-BOOTSTRAP-RANKING-CONTRACT.md`

## ROOT CAUSES ADDRESSED

- SessionStart V1 ranking previously used only type priority, quality and
  freshness even after current project state had been resolved.
- Equal scores depended on input/file order rather than a documented stable
  key.
- Malformed optional quality/timestamp/content fields could raise instead of
  degrading to bounded defaults.

## IMPLEMENTATION

When structured state is available, ranking uses the fixed formula:

```
0.30 * type_priority + 0.30 * quality + 0.15 * freshness
+ 0.25 * lexical_relevance
```

Without state/query text, the historical `0.40 / 0.40 / 0.20` formula is
preserved. State input is bounded to structured objective, phase, milestone,
requirements, work items, blockers, constraints and risks. Stable ordering uses
scope tier, descending score and a deterministic identity/content fallback.

## TESTS ADDED

- State-relevant memory outranks an equally scored unrelated memory.
- Equal-score memories keep the same identity order across input permutations.
- Malformed optional fields remain fail-soft with a deterministic score.

## TESTS EXECUTED

- Pre-change focused baseline: `tests/test_context_compiler.py` — **42 passed**.
- W-06A focused ranking suite — **47 passed**.
- Context/scope/router focused suite including cold SessionStart — **113
  passed**.
- Cold native SessionStart repeated independently — **5 passed**.
- Baseline snapshot integrity — **5 passed**.
- Full regression: `pytest tests -q` — **978 passed, 2 warnings**.
- Critical flake8 (`E9,F63,F7,F82`) on touched Python files — **PASS**.
- `compileall` on touched Python files — **PASS**.
- `git diff --check` — **PASS**.

The baseline refresh changed only `source_fingerprint`; the deterministic
baseline metrics remained `context_precision=0.18` and
`context_recall=0.8038461538461539` for 130 cases.

## QUALITY METRICS BEFORE/AFTER

- V1 bootstrap relevance: **unmeasured → covered by deterministic focused
  cases**.
- Equal-score ordering: **input-order dependent → stable identity/content key**.
- Existing V1 no-state ranking behavior: **preserved by regression suite**.
- Evaluation baseline metrics: **unchanged**; this package does not claim to
  pass the broader retrieval-quality gate.

## SAFETY METRICS

- Project-scope and retrieval-scope tests: PASS.
- Inactive-memory filtering: PASS.
- Context safety/privacy and canonical revision lineage tests: PASS.
- No new MemoryStore, StateStore or ProjectRegistry write path.
- No V2 promotion or Phase 20 change.

## KNOWN LIMITATIONS

This is only the bounded V1 SessionStart improvement. It uses deterministic
lexical overlap over resolved structured state; it does not solve full task-aware
retrieval, semantic paraphrase, embedding quality, V2 promotion, or daily-use
context quality. Those remain separate packages and evaluation gates.

## OPEN FAILURES

No new W-06A P0/P1 failure. The broader baseline still reports low retrieval
precision (`0.18`), which remains visible and is intentionally deferred to the
evaluation-backed retrieval work.

## INDEPENDENT REVIEW

The first independent review returned `FIX-FIRST` for missing state-query test
coverage and report trailing whitespace. Both findings were fixed in
`8270fef`; a fresh independent read-only review is still required and must
return exactly `SHIP`, `FIX-FIRST` or `RETHINK`.

## SCORE BEFORE/AFTER

- Retrieval quality: **4.5 → 5.0 provisional** (bounded V1 bootstrap evidence;
  not a graduation score).
- Context compilation: **6.0 → 6.3 provisional** (state relevance and stable
  ordering; V2 remains shadow).
- Scope/safety: **7.0 → 7.0** (no authority or isolation change).

**VERDICT:** `REVIEW PENDING`
